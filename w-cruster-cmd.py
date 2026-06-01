import glob
CSV_PATHS = sorted(glob.glob("../w-data/*.csv"))
SELECTED_TXT = "selected_columns.txt"
TILE_UNIT = "fail_type"; VIEW_BY = "axis"

for T in ["raw", "log", "binary"]:
    VALUE_TRANSFORM = T
    OUTPUT_HTML = f"report_{T}.html"
    OUTPUT_CSV  = f"tc_{T}.csv"
    exec(open("w_cluster_poc.py", encoding="utf-8").read())
