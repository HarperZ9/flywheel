# Training the 32B model on this machine

Date: 2026-07-09

## The constraint, stated plainly

This machine has 32 GB of system RAM. The 32B model is 82 GB in fp16 on disk.
Loading it and quantizing it to 4-bit for QLoRA streams roughly 20 GB through
system RAM at once. When the machine has close to 20 GB of RAM free, the load
completes in about 6 minutes and training runs at about 32 seconds per step.
When free RAM is low, the load swaps to disk and thrashes, which can make the
whole machine unresponsive.

This is a resource reality, not a bug. The 14B has no such trouble: it loads
and serves comfortably on ordinary free RAM. The 32B just needs the machine
close to idle.

## What proved it works

The 32B QLoRA smoke test passed on this machine: 2 optimizer steps, peak VRAM
21.24 GB on the 24 GB card, exit code 0, loaded in about 5 minutes 38 seconds.
The training path is sound. The only requirement is enough free RAM at load
time.

## How to run it

1. Close heavy applications (browser, chat, game launchers). Aim for at least
   about 22 GB of free RAM. You can check with:

   ```powershell
   [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)
   ```

2. Start the run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\launch_32b_training.ps1
   ```

   The supervisor waits on its own until about 22 GB of RAM is free, then it
   loads and trains. You can start it and walk away; if RAM is not free yet it
   simply waits and logs why.

3. Watch progress:

   ```powershell
   Get-Content E:\local-model-run\logs\phase2-32b-supervisor.log -Tail 5 -Wait
   ```

4. Stop it cleanly at any time:

   ```powershell
   New-Item E:\local-model-run\STOP_32B -ItemType File -Force
   ```

   The supervisor checks for that flag between attempts and exits without
   starting another.

## What the supervisor does for you

- Waits for a RAM gate (about 22 GB free) before each launch, so it never
  starts a load that would thrash. It polls every 2 minutes and logs the wait.
- Trains one quarter epoch, about 2,019 steps, which matches the recipe the
  shipped 14B artifact used (its checkpoint-2020).
- Checkpoints every 50 steps to
  `E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-32b`.
- Resumes automatically from the latest checkpoint if a run dies, up to 12
  attempts, so a multi-hour run survives a transient WSL hiccup.

## After training

The 32B follows the same release path the 14B did: merge the adapter, quantize
to GGUF, run the deterministic smoke, build the provenance chain, run the
endpoint gate and benchmark, then stage for release. It will not be published
until its evidence is something an outside observer can check, the same bar the
14B is held to.

## A note on the smaller-hardware goal

The direction of this project is more capability in less space. The 14B already
runs on an ordinary machine. The honest next steps for reaching smaller hardware
are lower-bit quantization of the trained artifacts (for example Q3_K_M for
machines with less memory) and, further out, distillation. Those belong on a
drive with room to spare; the earlier Q3 attempt filled the C: drive because it
wrote inside the WSL virtual disk, so future quantization should write its
output to E: instead.
