"""Explicit test harness. The injected engine emits a test tone, NOT speech."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.server import create_app
from fake_engine import DemoEngine
import uvicorn

parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,required=True)
parser.add_argument('--data',type=Path,required=True)
parser.add_argument('--fake-picker',action='store_true')
args=parser.parse_args()
picker=None
if args.fake_picker:
    # Explicitly simulated system-folder dialog for Linux browser CI.
    from model_fixtures import make_model
    model=make_model(args.data/'picker-model','voice_design')
    scan_a=args.data/'scan-A';scan_a.mkdir(exist_ok=True)
    scan_b=args.data/'scan-B';scan_b.mkdir(exist_ok=True)
    class FakeFolderPicker:
        def __init__(self):self.index=0
        def available(self):return True
        def pick(self,purpose,initial_path):
            if purpose=='model':
                import time
                time.sleep(.2)  # allow browser tests to close a dialog mid-selection
                return str(model)
            options=(str(scan_a),str(scan_b),str(scan_a),None)
            result=options[self.index%len(options)]
            self.index+=1
            return result
    picker=FakeFolderPicker()
app=create_app(Path(__file__).resolve().parents[1],args.data,demo=True,engine=DemoEngine(),folder_picker=picker)
uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning')
