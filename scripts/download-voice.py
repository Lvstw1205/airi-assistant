from pathlib import Path
from huggingface_hub import snapshot_download

root = Path(__file__).resolve().parents[1]
snapshot_download('mlx-community/whisper-large-v3-turbo', local_dir=str(root / '.runtime/models/whisper-turbo'), allow_patterns=['*.json', '*.safetensors', '*.npz'])
print('한국어 로컬 음성 모델 다운로드 완료')
