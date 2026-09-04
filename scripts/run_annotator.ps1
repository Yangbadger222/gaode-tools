param([string]$Region = "outputs/test_fixed_grid/region.json")
& .\.venv\Scripts\python.exe scripts\launch_annotator.py --region $Region
