@echo off
echo Installing required packages if not present...
python -m pip install PySide6 numpy PyOpenGL

echo Running BVH Viewer...
python bvh_viewer.py

pause
