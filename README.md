Here is a clean, markdown-ready README written entirely in standard text that you can copy and paste directly into your repository.

2D CWT Earthquake Signal Detection System
An advanced, GPU-accelerated signal processing and computer vision pipeline designed to detect seismic activity and earthquakes using acoustic data telemetry captured from underwater fiber-optic telecommunication cables.

By streaming raw acoustic datasets, mapping them into time-frequency spectrograms via 2D Continuous Wavelet Transform (CWT), and routing them through a YOLO object detection model, this system transforms raw subsurface vibrations into visual, localized earthquake classifications.

Pipeline Architecture
The throughput pipeline operates through the following stages:

Data Ingestion: The pipeline ingests raw, high-frequency acoustic data stored in HDF5 (.h5) format, capturing physical subsea cable vibrations.

GPU Batch Stacking: Data frames are pushed directly to the GPU in optimized memory blocks, where the GPU dynamically stacks the files to maximize parallel computing efficiency.

GPU Preprocessing & Signal Transformation:

The GPU handles low-level noise attenuation and baseline corrections across the stacked data arrays.

A parallelized 2D Continuous Wavelet Transform (CWT) shifts the time-domain telemetry into structural time-frequency data spaces.

Multi-Scale Filtering: The system applies varied scaling coefficients and distinct frequency filters to the transformed data, capturing multiple frequency layers of interest.

Batch Segmentation: The multi-scale signal data is separated into individual visual matrices.

YOLO Computer Vision Inference: These isolated segments are passed into a custom-trained YOLO algorithm. The model analyzes the patterns, detects anomalies, and outputs a final annotated image mapping spatial bounding boxes to definitive earthquake event classifications.

Key Performance Enhancements
Massive Parallel Speedup: Shifting the complex 2D CWT signal transformations and matrix operations directly into parallel GPU processing pipelines achieves a 6x speedup over traditional sequential CPU routines.

Multithreaded Execution: Leverages 4 concurrent processing threads to handle file ingest operations across distinct epochs, entirely removing disk bottlenecks.

Data Integrity Verification: Features integrated structural layers that track stacked output telemetry across preprocessing stages to detect and prevent data loss before final image generation.

Technical Stack
Language: Python

Signal Processing: 2D Continuous Wavelet Transform (CWT), Fast Fourier Transform (FFT)

Computer Vision & Deep Learning: YOLO Architecture, PyTorch

Data Handling: HDF5 Core Libraries, NumPy, CuPy / PyCUDA

Output Generation: OpenCV, Matplotlib

Getting Started
Prerequisites
NVIDIA GPU with CUDA Toolkit installed

Python 3.10+

Dependent Python packages: h5py, torch, ultralytics, numpy, opencv-python
