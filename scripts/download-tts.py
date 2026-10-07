from pathlib import Path
from supertonic import TTS
TTS(model_dir=Path(__file__).resolve().parents[1]/'.runtime/models/supertonic-3',auto_download=True,intra_op_num_threads=4,inter_op_num_threads=1)
print('Supertonic 3 local voices ready')
