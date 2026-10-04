// SPDX-License-Identifier: CERN-OHL-S-2.0
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

#include "pico/stdlib.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/spi.h"
#include "hardware/sync.h"


namespace {

// -----------------------------------------------------------------------------
// Board mapping: RP2040 QFN56 / SPI1 valid pin group.
// -----------------------------------------------------------------------------

spi_inst_t *const kAdcSpi = spi1;

constexpr uint kPinSpiMiso = 8;   // SPI1 RX
constexpr uint kPinAdcCs = 9;     // GPIO-controlled SPI1 CSn
constexpr uint kPinSpiSck = 10;   // SPI1 SCK
constexpr uint kPinSpiMosi = 11;  // SPI1 TX

constexpr uint kPinAdcDrdy = 12;
constexpr uint kPinAdcSyncReset = 13;

constexpr uint kPinMuxA0 = 2;
constexpr uint kPinMuxA1 = 3;
constexpr uint kPinMuxA2 = 4;
constexpr uint kPinMuxA3 = 5;
constexpr uint kPinMuxEnable = 6;

// -----------------------------------------------------------------------------
// Acquisition model.
// -----------------------------------------------------------------------------

constexpr unsigned kBankCount = 8;
constexpr unsigned kChannelsPerBank = 16;
constexpr unsigned kEegChannels = 128;

constexpr unsigned kDiscardConversions = 4;
constexpr unsigned kKeepConversions = 4;
constexpr unsigned kConversionsPerSlot =
    kDiscardConversions + kKeepConversions;

static_assert(kConversionsPerSlot == 8);

constexpr unsigned kAdcFrameWords = 10;  // response + 8 channels + CRC
constexpr unsigned kAdcWordBytes = 4;
constexpr unsigned kAdcFrameBytes = kAdcFrameWords * kAdcWordBytes;

constexpr uint32_t kLogicalRateHz = 250;
constexpr uint32_t kCalibrationFrames = 500;

// -----------------------------------------------------------------------------
// ADS131M08 configuration.
//
// CLKIN is a dedicated 8.192-MHz CMOS oscillator connected to pin 23.
// CLOCK:
//   channels enabled = 0xFF00
//   XTAL_DIS = 1 because CLKIN is externally driven
//   EXTREF_EN = 0, internal 1.2-V reference
//   OSR = 000 = 128
//   PWR = 10 = HR
//
// MODE:
//   RESET status clear
//   WLENGTH = 11 = 32-bit sign-extended conversion words
//   TIMEOUT = 1
//   DRDY_FMT = 1 = active-low pulse
//
// GAIN1/GAIN2:
//   PGAGAIN = 010 = gain 4 for every channel.
// -----------------------------------------------------------------------------

constexpr uint8_t kRegMode = 0x02;
constexpr uint8_t kRegClock = 0x03;
constexpr uint8_t kRegGain1 = 0x04;
constexpr uint8_t kRegGain2 = 0x05;

constexpr uint16_t kClock32kSpsExternalClock = 0xFF82;
constexpr uint16_t kMode32BitSignExtend = 0x0311;
constexpr uint16_t kGainAll4 = 0x2222;

// SPI is intentionally well below the ADS131M08 digital-interface maximum.
constexpr uint32_t kSpiBaudHz = 12'000'000;

// -----------------------------------------------------------------------------
// Existing P1/P2 transport format.
// -----------------------------------------------------------------------------

constexpr uint32_t kBciMagic = 0x31494342u;  // "BCI1" little-endian
constexpr uint16_t kBciProtocol = 0x0100;
constexpr uint16_t kBciHeaderBytes = 128;

constexpr uint32_t kFlagEegPresent = 1u << 0;
constexpr uint32_t kFlagTimestampValid = 1u << 3;
constexpr uint32_t kFlagCalibrated = 1u << 5;

#pragma pack(push, 1)

struct BciPacketHeader {
    uint32_t magic;
    uint16_t protocol_version;
    uint16_t header_bytes;
    uint32_t packet_bytes;
    uint32_t sequence;
    uint64_t timestamp_ns;
    uint32_t flags;
    uint32_t status;
    uint32_t eeg_channel_mask[4];
    uint32_t meg_channel_mask[4];
    uint16_t eeg_channel_count;
    uint16_t meg_channel_count;
    uint16_t fnirs_long_count;
    uint16_t fnirs_short_count;
    uint8_t fnirs_wavelength_count;
    uint8_t sample_format;
    uint16_t reserved0;
    uint8_t reserved[44];
    uint32_t payload_crc32c;
    uint32_t header_crc32c;
};

struct BciFastPacket {
    BciPacketHeader header;
    int32_t eeg[kEegChannels];
    int32_t meg[kEegChannels];
};

#pragma pack(pop)

static_assert(sizeof(BciPacketHeader) == 128);
static_assert(sizeof(BciFastPacket) == 1152);

struct Calibration {
    int64_t offset;
    int32_t gain_q30;
};

// -----------------------------------------------------------------------------
// State.
// -----------------------------------------------------------------------------

alignas(4) uint8_t g_spi_tx[kAdcFrameBytes] = {};
alignas(4) uint8_t g_spi_rx[kAdcFrameBytes] = {};

int g_dma_tx = -1;
int g_dma_rx = -1;

volatile bool g_spi_busy = false;
volatile uint8_t g_mux_position = 0;
volatile uint8_t g_sample_in_slot = 0;

std::array<int64_t, kBankCount> g_accumulation = {};
std::array<int32_t, kEegChannels> g_eeg_frame = {};
std::array<Calibration, kEegChannels> g_calibration = {};
std::array<int64_t, kEegChannels> g_calibration_sum = {};

uint32_t g_calibration_frames = 0;
bool g_calibration_complete = false;
uint32_t g_packet_sequence = 0;

// -----------------------------------------------------------------------------
// CRC32C / Castagnoli.
// -----------------------------------------------------------------------------

uint32_t Crc32c(
    uint32_t initial,
    const void *data,
    std::size_t length
) {
    const auto *p = static_cast<const uint8_t *>(data);
    uint32_t crc = ~initial;

    for (std::size_t i = 0; i < length; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            const uint32_t mask =
                static_cast<uint32_t>(
                    -static_cast<int32_t>(crc & 1u)
                );
            crc = (crc >> 1u) ^ (0x82F63B78u & mask);
        }
    }
    return ~crc;
}

uint64_t TimestampNs() {
    return static_cast<uint64_t>(time_us_64()) * 1000ull;
}

int32_t BigEndianSigned32(const uint8_t *p) {
    const uint32_t value =
        (static_cast<uint32_t>(p[0]) << 24u) |
        (static_cast<uint32_t>(p[1]) << 16u) |
        (static_cast<uint32_t>(p[2]) << 8u) |
        static_cast<uint32_t>(p[3]);
    return static_cast<int32_t>(value);
}

// -----------------------------------------------------------------------------
// MUX.
// -----------------------------------------------------------------------------

void SetMuxEnabled(bool enabled) {
    // CD74HC4067 enable is active low.
    gpio_put(kPinMuxEnable, enabled ? 0 : 1);
}

void SelectMux(uint8_t channel) {
    SetMuxEnabled(false);

    gpio_put(kPinMuxA0, (channel >> 0u) & 1u);
    gpio_put(kPinMuxA1, (channel >> 1u) & 1u);
    gpio_put(kPinMuxA2, (channel >> 2u) & 1u);
    gpio_put(kPinMuxA3, (channel >> 3u) & 1u);

    busy_wait_us_32(2);
    SetMuxEnabled(true);
}

// -----------------------------------------------------------------------------
// ADS131M08 configuration.
// -----------------------------------------------------------------------------

void AdcCs(bool asserted) {
    gpio_put(kPinAdcCs, asserted ? 0 : 1);
}

void WriteRegister24(uint8_t address, uint16_t value) {
    // WREG format: 011a aaaa annn nnnn, n=0 for one register.
    const uint16_t command =
        static_cast<uint16_t>(0x6000u | (static_cast<uint16_t>(address) << 7u));

    // During startup the ADC uses default 24-bit communication words.
    // A complete normal frame is still clocked so no pending conversion frame
    // is accidentally truncated.
    uint8_t frame[30] = {};
    frame[0] = static_cast<uint8_t>(command >> 8u);
    frame[1] = static_cast<uint8_t>(command);
    frame[2] = 0;

    frame[3] = static_cast<uint8_t>(value >> 8u);
    frame[4] = static_cast<uint8_t>(value);
    frame[5] = 0;

    AdcCs(true);
    spi_write_blocking(kAdcSpi, frame, sizeof(frame));
    AdcCs(false);
    busy_wait_us_32(10);
}

void SynchronizeAdc() {
    // 2 us at 8.192 MHz is about 16 CLKIN cycles and remains far below
    // the 2048-CLKIN reset threshold.
    gpio_put(kPinAdcSyncReset, 0);
    busy_wait_us_32(2);
    gpio_put(kPinAdcSyncReset, 1);
}

void ConfigureAdc() {
    AdcCs(false);
    gpio_put(kPinAdcSyncReset, 1);
    sleep_ms(20);

    WriteRegister24(kRegClock, kClock32kSpsExternalClock);
    WriteRegister24(kRegGain1, kGainAll4);
    WriteRegister24(kRegGain2, kGainAll4);

    // MODE is written last because it changes the communication word length.
    WriteRegister24(kRegMode, kMode32BitSignExtend);

    sleep_ms(2);
    SynchronizeAdc();
}

// -----------------------------------------------------------------------------
// Calibration.
// -----------------------------------------------------------------------------

int32_t ApplyCalibration(unsigned channel, int32_t raw) {
    const Calibration &cal = g_calibration[channel];
    const int64_t centered = static_cast<int64_t>(raw) - cal.offset;
    const int64_t corrected =
        (centered * static_cast<int64_t>(cal.gain_q30)) >> 30;

    if (corrected > std::numeric_limits<int32_t>::max()) {
        return std::numeric_limits<int32_t>::max();
    }
    if (corrected < std::numeric_limits<int32_t>::min()) {
        return std::numeric_limits<int32_t>::min();
    }
    return static_cast<int32_t>(corrected);
}

void UpdateStartupOffsetCalibration() {
    if (g_calibration_complete) {
        return;
    }

    for (unsigned channel = 0; channel < kEegChannels; ++channel) {
        g_calibration_sum[channel] += g_eeg_frame[channel];
    }

    ++g_calibration_frames;
    if (g_calibration_frames < kCalibrationFrames) {
        return;
    }

    for (unsigned channel = 0; channel < kEegChannels; ++channel) {
        g_calibration[channel].offset =
            g_calibration_sum[channel] / static_cast<int64_t>(kCalibrationFrames);
        g_calibration[channel].gain_q30 = 1 << 30;
    }

    g_calibration_complete = true;
}

// -----------------------------------------------------------------------------
// Transport.
// -----------------------------------------------------------------------------

void EmitPacket() {
    static BciFastPacket packet;
    std::memset(&packet, 0, sizeof(packet));

    packet.header.magic = kBciMagic;
    packet.header.protocol_version = kBciProtocol;
    packet.header.header_bytes = kBciHeaderBytes;
    packet.header.packet_bytes = sizeof(packet);
    packet.header.sequence = g_packet_sequence++;
    packet.header.timestamp_ns = TimestampNs();
    packet.header.flags =
        kFlagEegPresent |
        kFlagTimestampValid |
        (g_calibration_complete ? kFlagCalibrated : 0u);

    for (uint32_t &word : packet.header.eeg_channel_mask) {
        word = 0xFFFFFFFFu;
    }
    packet.header.eeg_channel_count = kEegChannels;
    packet.header.sample_format = 1;  // S32 little endian

    for (unsigned channel = 0; channel < kEegChannels; ++channel) {
        packet.eeg[channel] =
            ApplyCalibration(channel, g_eeg_frame[channel]);
    }

    packet.header.payload_crc32c =
        Crc32c(
            0,
            reinterpret_cast<const uint8_t *>(&packet) + kBciHeaderBytes,
            sizeof(packet) - kBciHeaderBytes
        );

    packet.header.header_crc32c =
        Crc32c(
            0,
            &packet.header,
            offsetof(BciPacketHeader, header_crc32c)
        );

    const auto *bytes = reinterpret_cast<const uint8_t *>(&packet);
    for (std::size_t i = 0; i < sizeof(packet); ++i) {
        stdio_putchar_raw(bytes[i]);
    }
}

// -----------------------------------------------------------------------------
// SPI DMA.
// -----------------------------------------------------------------------------

void StartSpiDma() {
    if (g_spi_busy) {
        return;
    }
    g_spi_busy = true;
    std::memset(g_spi_tx, 0, sizeof(g_spi_tx));

    AdcCs(true);

    dma_channel_set_read_addr(g_dma_tx, g_spi_tx, false);
    dma_channel_set_write_addr(g_dma_rx, g_spi_rx, false);
    dma_channel_set_trans_count(g_dma_rx, kAdcFrameBytes, false);
    dma_channel_set_trans_count(g_dma_tx, kAdcFrameBytes, false);

    dma_start_channel_mask(
        (1u << static_cast<unsigned>(g_dma_rx)) |
        (1u << static_cast<unsigned>(g_dma_tx))
    );
}

void ProcessAdcFrame() {
    if (g_sample_in_slot >= kDiscardConversions) {
        for (unsigned bank = 0; bank < kBankCount; ++bank) {
            const std::size_t byte_offset = (1u + bank) * kAdcWordBytes;
            g_accumulation[bank] += BigEndianSigned32(&g_spi_rx[byte_offset]);
        }
    }

    ++g_sample_in_slot;
    if (g_sample_in_slot < kConversionsPerSlot) {
        return;
    }

    for (unsigned bank = 0; bank < kBankCount; ++bank) {
        const unsigned logical_channel =
            bank * kChannelsPerBank + g_mux_position;

        g_eeg_frame[logical_channel] =
            static_cast<int32_t>(
                g_accumulation[bank] /
                static_cast<int64_t>(kKeepConversions)
            );
        g_accumulation[bank] = 0;
    }

    g_sample_in_slot = 0;
    ++g_mux_position;

    if (g_mux_position >= kChannelsPerBank) {
        g_mux_position = 0;
        UpdateStartupOffsetCalibration();
        EmitPacket();
    }

    SelectMux(g_mux_position);
    SynchronizeAdc();
}

void DmaIrqHandler() {
    const uint32_t rx_mask = 1u << static_cast<unsigned>(g_dma_rx);
    if ((dma_hw->ints0 & rx_mask) == 0) {
        return;
    }

    dma_hw->ints0 = rx_mask;
    dma_channel_wait_for_finish_blocking(g_dma_tx);
    AdcCs(false);
    g_spi_busy = false;
    ProcessAdcFrame();
}

void DrdyIrq(uint gpio, uint32_t events) {
    if (
        gpio == kPinAdcDrdy &&
        (events & GPIO_IRQ_EDGE_FALL) != 0u
    ) {
        StartSpiDma();
    }
}

// -----------------------------------------------------------------------------
// Hardware startup.
// -----------------------------------------------------------------------------

void InitOutput(uint pin, bool value) {
    gpio_init(pin);
    gpio_set_dir(pin, GPIO_OUT);
    gpio_put(pin, value);
}

void InitHardware() {
    InitOutput(kPinAdcCs, true);
    InitOutput(kPinAdcSyncReset, true);
    InitOutput(kPinMuxA0, false);
    InitOutput(kPinMuxA1, false);
    InitOutput(kPinMuxA2, false);
    InitOutput(kPinMuxA3, false);
    InitOutput(kPinMuxEnable, true);

    gpio_init(kPinAdcDrdy);
    gpio_set_dir(kPinAdcDrdy, GPIO_IN);

    spi_init(kAdcSpi, kSpiBaudHz);
    spi_set_format(
        kAdcSpi,
        8,
        SPI_CPOL_0,
        SPI_CPHA_1,
        SPI_MSB_FIRST
    );

    gpio_set_function(kPinSpiMiso, GPIO_FUNC_SPI);
    gpio_set_function(kPinSpiSck, GPIO_FUNC_SPI);
    gpio_set_function(kPinSpiMosi, GPIO_FUNC_SPI);

    g_dma_tx = dma_claim_unused_channel(true);
    g_dma_rx = dma_claim_unused_channel(true);

    dma_channel_config tx = dma_channel_get_default_config(g_dma_tx);
    channel_config_set_transfer_data_size(&tx, DMA_SIZE_8);
    channel_config_set_dreq(&tx, spi_get_dreq(kAdcSpi, true));
    channel_config_set_read_increment(&tx, true);
    channel_config_set_write_increment(&tx, false);
    dma_channel_configure(
        g_dma_tx,
        &tx,
        &spi_get_hw(kAdcSpi)->dr,
        g_spi_tx,
        0,
        false
    );

    dma_channel_config rx = dma_channel_get_default_config(g_dma_rx);
    channel_config_set_transfer_data_size(&rx, DMA_SIZE_8);
    channel_config_set_dreq(&rx, spi_get_dreq(kAdcSpi, false));
    channel_config_set_read_increment(&rx, false);
    channel_config_set_write_increment(&rx, true);
    dma_channel_configure(
        g_dma_rx,
        &rx,
        g_spi_rx,
        &spi_get_hw(kAdcSpi)->dr,
        0,
        false
    );

    dma_channel_set_irq0_enabled(g_dma_rx, true);
    irq_set_exclusive_handler(DMA_IRQ_0, DmaIrqHandler);
    irq_set_enabled(DMA_IRQ_0, true);

    gpio_set_irq_enabled_with_callback(
        kPinAdcDrdy,
        GPIO_IRQ_EDGE_FALL,
        true,
        &DrdyIrq
    );
}

}  // namespace


int main() {
    stdio_init_all();
    sleep_ms(1200);

    for (Calibration &cal : g_calibration) {
        cal.offset = 0;
        cal.gain_q30 = 1 << 30;
    }

    InitHardware();
    SelectMux(0);
    ConfigureAdc();

    g_mux_position = 0;
    g_sample_in_slot = 0;
    g_accumulation.fill(0);
    SelectMux(0);
    SynchronizeAdc();

    while (true) {
        __wfi();
    }
}
