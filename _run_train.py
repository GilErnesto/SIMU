import sys, types
m=types.ModuleType("matplotlib"); m.font_manager=types.SimpleNamespace(); m.__path__=[]
sys.modules["matplotlib"]=m; sys.modules["matplotlib.font_manager"]=m.font_manager
from training.train import main
raise SystemExit(main(["--config","training/configs/ouro.yaml"]))
