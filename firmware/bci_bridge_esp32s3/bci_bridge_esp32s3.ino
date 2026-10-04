// SPDX-License-Identifier: CERN-OHL-S-2.0
#include <Arduino.h>
#include <esp_timer.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static constexpr uint32_t BCI_SAMPLE_RATE_HZ = 250;
static constexpr size_t BCI_ANALOG_CHANNELS = 8;
static constexpr size_t BCI_DIGITAL_CHANNELS = 4;
static constexpr uint8_t kAnalogPins[BCI_ANALOG_CHANNELS] = {1,2,3,4,5,6,7,8};
static constexpr uint8_t kDigitalPins[BCI_DIGITAL_CHANNELS] = {11,12,13,14};

static constexpr uint32_t BCI_PACKET_MAGIC = 0x31494342UL;
static constexpr uint16_t BCI_PROTOCOL_VERSION = 0x0100;
static constexpr uint16_t BCI_HEADER_BYTES = 128;
static constexpr uint8_t BCI_SAMPLE_S32_LE = 1;
static constexpr uint32_t BCI_FLAG_EEG_PRESENT = 1UL << 0;
static constexpr uint32_t BCI_FLAG_TIMESTAMP_VALID = 1UL << 3;
static constexpr uint32_t BCI_FLAG_CALIBRATED = 1UL << 5;
static constexpr uint32_t BCI_FLAG_BRIDGE_PAYLOAD = 1UL << 15;

#pragma pack(push, 1)
struct bci_packet_header_t {
    uint32_t magic;
    uint16_t protocol_version, header_bytes;
    uint32_t packet_bytes, sequence;
    uint64_t timestamp_ns;
    uint32_t flags, status;
    uint32_t eeg_channel_mask[4], meg_channel_mask[4];
    uint16_t eeg_channel_count, meg_channel_count, fnirs_long_count, fnirs_short_count;
    uint8_t fnirs_wavelength_count, sample_format;
    uint16_t reserved0;
    uint8_t reserved[44];
    uint32_t payload_crc32c, header_crc32c;
};
struct bci_bridge_payload_t {
    int32_t analog[BCI_ANALOG_CHANNELS];
    uint32_t digital_bits;
    uint32_t sample_counter;
};
struct bci_bridge_packet_t {
    bci_packet_header_t header;
    bci_bridge_payload_t payload;
};
#pragma pack(pop)

static_assert(sizeof(bci_packet_header_t) == 128);
static_assert(sizeof(bci_bridge_packet_t) == 168);

static uint32_t crc32c(uint32_t initial, const void *data, size_t n) {
    auto p = static_cast<const uint8_t *>(data);
    uint32_t crc = ~initial;
    while (n--) {
        crc ^= *p++;
        for (unsigned i=0;i<8;i++) {
            const uint32_t mask = static_cast<uint32_t>(-static_cast<int32_t>(crc & 1U));
            crc = (crc >> 1U) ^ (0x82F63B78UL & mask);
        }
    }
    return ~crc;
}

static uint32_t sequence_no = 0;
static uint32_t sample_counter = 0;

static void buildPacket(bci_bridge_packet_t &p) {
    memset(&p, 0, sizeof(p));
    p.header.magic = BCI_PACKET_MAGIC;
    p.header.protocol_version = BCI_PROTOCOL_VERSION;
    p.header.header_bytes = BCI_HEADER_BYTES;
    p.header.packet_bytes = sizeof(p);
    p.header.sequence = sequence_no++;
    p.header.timestamp_ns = static_cast<uint64_t>(esp_timer_get_time()) * 1000ULL;
    p.header.flags = BCI_FLAG_EEG_PRESENT | BCI_FLAG_TIMESTAMP_VALID | BCI_FLAG_CALIBRATED | BCI_FLAG_BRIDGE_PAYLOAD;
    p.header.eeg_channel_mask[0] = 0xFF;
    p.header.eeg_channel_count = BCI_ANALOG_CHANNELS;
    p.header.sample_format = BCI_SAMPLE_S32_LE;
    for (size_t i=0;i<BCI_ANALOG_CHANNELS;i++) p.payload.analog[i] = analogRead(kAnalogPins[i]);
    for (size_t i=0;i<BCI_DIGITAL_CHANNELS;i++) if (digitalRead(kDigitalPins[i]) == LOW) p.payload.digital_bits |= 1UL << i;
    p.payload.sample_counter = sample_counter++;
    p.header.payload_crc32c = crc32c(0, &p.payload, sizeof(p.payload));
    p.header.header_crc32c = crc32c(0, &p.header, offsetof(bci_packet_header_t, header_crc32c));
}

void setup() {
    analogReadResolution(12);
    for (auto pin : kAnalogPins) pinMode(pin, INPUT);
    for (auto pin : kDigitalPins) pinMode(pin, INPUT_PULLUP);
    Serial.begin(921600);
    delay(250);
}

void loop() {
    static int64_t next_us = esp_timer_get_time();
    static bci_bridge_packet_t p;
    constexpr int64_t period_us = 1000000LL / BCI_SAMPLE_RATE_HZ;
    const int64_t now = esp_timer_get_time();
    if (now < next_us) return;
    next_us += period_us;
    buildPacket(p);
    Serial.write(reinterpret_cast<const uint8_t *>(&p), sizeof(p));
}
