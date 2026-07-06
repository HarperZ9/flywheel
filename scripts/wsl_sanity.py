import torch, transformers, peft, accelerate, trl, bitsandbytes
print("torch       ", torch.__version__, "| cuda?", torch.cuda.is_available(),
      "|", (torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU"))
print("transformers", transformers.__version__)
print("peft        ", peft.__version__)
print("accelerate  ", accelerate.__version__)
print("trl         ", trl.__version__)
print("bitsandbytes", bitsandbytes.__version__)
if torch.cuda.is_available():
    free, total = torch.cuda.mem_get_info()
    print(f"GPU VRAM free={free/1e9:.1f}GB total={total/1e9:.1f}GB")
