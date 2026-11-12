"""[Example] Variance of the sample mean vs n. Usage: python run.py"""
import json
import random
import statistics

import yaml

cfg = yaml.safe_load(open("config.yaml"))
random.seed(cfg["seed"])
out = {}
for n in cfg["n"]:
    means = [statistics.fmean(random.gauss(0, 1) for _ in range(n)) for _ in range(cfg["repetitions"])]
    out[n] = statistics.pvariance(means)
json.dump(out, open("results.json", "w"), indent=1)
print(out)
