try:
    import cupy as cp
    print("CuPy imported successfully")
    print(f"GPU: {cp.cuda.runtime.getDeviceProperties(0)['name'].decode()}")
    
    # Quick test
    a = cp.ones((1000, 1000), dtype=cp.float32)
    b = cp.fft.rfft2(a)
    print(f"rfft2 output shape: {b.shape}")
    print("GPU FFT works!")
except ImportError as e:
    print(f"CuPy import failed: {e}")