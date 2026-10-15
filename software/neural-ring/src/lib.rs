// SPDX-License-Identifier: AGPL-3.0-only
//! Preallocated bounded ring. C callers own buffer validity and handle lifetime.
use std::sync::Mutex;

pub struct Ring {
    samples: Vec<f32>,
    timestamps: Vec<f64>,
    channels: usize,
    capacity: usize,
    head: usize,
    count: usize,
    dropped: u64,
    last: f64,
}

#[no_mangle]
pub extern "C" fn nbfm_ring_new(capacity: usize, channels: usize) -> *mut Mutex<Ring> {
    let Some(size) = capacity.checked_mul(channels) else { return std::ptr::null_mut() };
    if capacity == 0 || channels == 0 || size > 16_777_216 { return std::ptr::null_mut() }
    Box::into_raw(Box::new(Mutex::new(Ring { samples: vec![0.;size],
        timestamps: vec![0.;capacity], channels, capacity, head:0, count:0,
        dropped:0, last:f64::NEG_INFINITY })))
}

/// # Safety
/// Handle must be live; arrays hold rows*channels floats and rows timestamps.
#[no_mangle]
pub unsafe extern "C" fn nbfm_ring_push(handle: *mut Mutex<Ring>, data: *const f32,
    times: *const f64, rows: usize) -> bool {
    if handle.is_null() || data.is_null() || times.is_null() { return false }
    let Ok(mut ring) = (*handle).lock() else { return false };
    let Some(values) = rows.checked_mul(ring.channels) else { return false };
    if rows > 1_048_576 || values > 16_777_216 { return false }
    let x = std::slice::from_raw_parts(data,values);
    let t = std::slice::from_raw_parts(times,rows);
    if !x.iter().all(|v| v.is_finite()) || !t.iter().all(|v| v.is_finite())
        || t.windows(2).any(|w| w[1] <= w[0]) || t.first().is_some_and(|v| *v<=ring.last)
        { return false }
    let channels = ring.channels;
    for (i, stamp) in t.iter().enumerate() {
        if ring.count == ring.capacity {
            ring.head = (ring.head+1)%ring.capacity;
            ring.count -= 1; ring.dropped += 1;
        }
        let index = (ring.head+ring.count)%ring.capacity;
        ring.samples[index*channels..(index+1)*channels]
            .copy_from_slice(&x[i*channels..(i+1)*channels]);
        ring.timestamps[index] = *stamp;
        ring.last = *stamp; ring.count += 1;
    }
    true
}

/// # Safety
/// Handle is live; output arrays hold maximum*channels floats and maximum times.
#[no_mangle]
pub unsafe extern "C" fn nbfm_ring_pop(handle: *mut Mutex<Ring>, data: *mut f32,
    times: *mut f64, maximum: usize) -> usize {
    if handle.is_null() || data.is_null() || times.is_null() { return 0 }
    let Ok(mut ring) = (*handle).lock() else { return 0 };
    let count = maximum.min(ring.count);
    for i in 0..count {
        let index = (ring.head+i)%ring.capacity;
        std::ptr::copy_nonoverlapping(ring.samples.as_ptr().add(index*ring.channels),
                                      data.add(i*ring.channels),ring.channels);
        *times.add(i) = ring.timestamps[index];
    }
    ring.head = (ring.head+count)%ring.capacity; ring.count -= count;
    count
}

/// # Safety
/// Handle must be live, or null.
#[no_mangle]
pub unsafe extern "C" fn nbfm_ring_dropped(handle: *mut Mutex<Ring>) -> u64 {
    if handle.is_null() { return 0 }
    (*handle).lock().map(|r| r.dropped).unwrap_or(u64::MAX)
}

/// # Safety
/// Free exactly once, after every producer/consumer call has completed.
#[no_mangle]
pub unsafe extern "C" fn nbfm_ring_free(handle: *mut Mutex<Ring>) {
    if !handle.is_null() { drop(Box::from_raw(handle)); }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn wrap_loss_and_timestamp_rejection() {
        unsafe {
            let r=nbfm_ring_new(2,2);
            assert!(nbfm_ring_push(r,[1.,2.,3.,4.,5.,6.].as_ptr(),[1.,2.,3.].as_ptr(),3));
            assert_eq!(nbfm_ring_dropped(r),1);
            assert!(!nbfm_ring_push(r,[9.,9.].as_ptr(),[2.].as_ptr(),1));
            let mut data=[0.;4]; let mut times=[0.;2];
            assert_eq!(nbfm_ring_pop(r,data.as_mut_ptr(),times.as_mut_ptr(),2),2);
            assert_eq!(data,[3.,4.,5.,6.]); assert_eq!(times,[2.,3.]);
            nbfm_ring_free(r);
        }
    }
    #[test]
    fn reject_overflow_dimensions() {
        assert!(nbfm_ring_new(usize::MAX,2).is_null());
        assert!(nbfm_ring_new(0,128).is_null());
    }
}
