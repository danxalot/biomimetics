import os
from transformers import AutoModel, AutoProcessor

model_name = "google/siglip-2-so400m-patch14-384"
save_directory = "./models/siglip"

if not os.path.exists(save_directory):
    os.makedirs(save_directory)

print(f"Downloading {model_name} to {save_directory}...")
model = AutoModel.from_pretrained(model_name)
processor = AutoProcessor.from_pretrained(model_name)

model.save_pretrained(save_directory)
processor.save_pretrained(save_directory)
print("Download complete.")
