
# gpu-unlock vs. a local LLM on Ryzen 7 7800X3D + RTX 4060 Ti 8GB (Windows 11 bare metal)

**Verdict up front:** the project is real, the mechanism is real, and the 4060 Ti **is** in its device table — but for the workload in the question (a quantized GGUF chat model served from 8 GB of GDDR6) the expected speed-up is **≈0 %**, because llama.cpp's quantized matmuls never touch the throttled instruction path this unlock un-caps. The unlock cannot add VRAM or bandwidth, which are the two things that actually bind on this card. Numbers, sources and the reasoning are below.

Analysis target: `repos/gpu-unlock` (HEAD `7eb51bc`, VERSION 2.0.0, GPL-2.0-only, 12 731 stars) plus the machine itself, which was inspected directly (§2 for measured host facts).

---

## 1. What the code actually does (source-verified)

The claim in `README.md:7` — "**Up to 2× FP16 / BF16 / TF32 tensor throughput**" — is mechanically accurate. NVIDIA ships GeForce silicon with FP16/BF16/TF32 **MMA with FP32 accumulation** running at half the rate of the same silicon in an A-series card (`README.md:13-15`). The limiter is a per-speed-class override register gated by a privilege-level mask:

- `FEAT_OVR_SM_SPD` (SS0) `0x0082381c`, default `0x00000001`, holds eight 4-bit speed selectors (DP, FFMA, FMLA16, FMLA32, IMLA0-3); `FEAT_OVR_SM_SPD_1` (SS1) `0x00823820` holds one more for IMLA4. Encoding: bit 3 = override enable, bits 2:0 = 00 full / 01 half / 10 quarter / 11 eighth (`docs/How Ampere was unlocked.md:158-172`, `kernel/gpu_unlock/registers.h:96-98`).
- Host writes to SS0/SS1 are silently dropped: `FEAT_OVR_PLM` (`0x00823804`) defaults to `0xffffff8f` — bits [7:4] = `1000` mean **only privilege level 3 (heavy-secure) may write** (`docs/How Ampere was unlocked.md:183-190`).

So the module does three things per card, all before the stock driver binds (`main.c:165-200`, run from initramfs, which must finish before `nvidia` loads — `main.c:192`):

1. **ROP into the SEC2 booter.** A stack overflow in the signed SEC2 Booter firmware yields one arbitrary write primitive (`docs/How Ampere was unlocked.md:85-98`). The payload is a six-write ROP chain built from fixed booter offsets — GA102: entry `0x1110`, canary `0x6140`, frames from `0xff54`, exit `0x81ee` (`recipes.c:25-53`); Ada: `0x257e`, `0x5f50`, exit `0x771e` (`recipes.c:70-123`).
2. **Raise the PLM to `0xffffffff`** for `FEAT_PLM` (and on Ada `WPR_CFG`, `WPR`, optionally `FBPA`) so the selector registers become host-writable (`recipes.c:192-197`).
3. **Write the selectors from the host** — `SS0 = 0x88888888`, `SS1 = 0x8` (`recipes.c:225-228`, `unlock_610.c:1349-1392`) — then issue a **PCIe FLR** (`unlock_610.c:1463-1572`) so the tampered firmware state is forgotten and the unmodified driver gets a clean handover.

Two details matter for §6: the WPR2 metadata's signature fields are **re-pointed at the attacker's own `0xfa00`-byte buffer** (`unlock_610.c:1125-1154`) instead of the stock signature, and the FWSEC-FRTS firmware blob carved out of the board VBIOS is **patched** before launch (`vbios_610.c:341-375`, `unlock_610.c:775-926`). This is a firmware-authentication bypass, not a register poke. `firmware/NOTICE.md` is candid about the state of the art:

> "The payload reference targets GA100 CMP 170HX. It does not establish GA10x firmware acceptance, standalone multiwrite, final FLR retention or stock-driver handover. Those require the Stage 1 hardware experiments."

…and `firmware/README.md:17` points at `docs/STAGE1.md`, **which does not exist in the tree** — `docs/` contains exactly one file, `How Ampere was unlocked.md`.

---

## 2. Can it run on *this* machine at all? (measured, not assumed)

Host facts gathered on the box (`nvidia-smi`, `pwsh`, `Get-CimInstance`):

| Fact | Value |
| --- | --- |
| OS / firmware | Windows 11 Pro 26100, **UEFI**, **Secure Boot = False**, BitLocker `FullyDecrypted` / `Off` |
| CPU / board | Ryzen 7 7800X3D 8C/16T; **Gigabyte B650M AORUS ELITE AX ICE**, AMI BIOS **F34** (2025-03-12) |
| RAM | 2 × 16 GB DDR5, configured **6000 MT/s** |
| GPU | RTX 4060 Ti, 8188 MiB, driver **616.92**, power limit **185.00 W**, idle SM clock 2580 MHz |
| Displays | **Monitor is on the AMD Radeon iGPU at 2560×1440**; NVIDIA `display_active = Disabled` |
| VRAM in use | 124 MiB (OBS / QQ / GameViewer attached, not displaying) |
| WSL | **not installed** |
| Disks | Disk 0 GPT 1 TB (ESP = 300 MiB), Disk 1 MBR 1 TB; **C: free 202 GB**, D: 258 GB, E: 112 GB |

**Windows native: impossible.** `gpu_unlock` is an out-of-tree Linux kernel module (DKMS, `kernel/gpu_unlock/Kbuild`, loaded from initramfs ahead of `nvidia`). It calls `pci_iomap` on BAR0, issues `pcie_flr`, and requires `pdev->driver == NULL` (`main.c:47-61`). There is no Windows kernel-mode component in this repository. `README.md:37`: "Linux only."

**WSL2: impossible, and not for political reasons.** WSL2's CUDA is paravirtualised through `/dev/dxg` (Microsoft's `dxgkrnl`), which exposes no PCIe device, no config space, and no BAR0. There is no `10de:2803` device to `pci_get_device()`, no MMIO window to write, and no FLR to issue. The unlock needs all three. (WSL is not even installed here.)

**Dual boot: viable, and it is the only Linux path.** Room to spare (202 GB free on the GPT disk 0), Secure Boot already off, and — importantly — **the 4060 Ti is not the display adapter**. The module does support the display card, but it must tear the framebuffer down before the FLR and the screen goes blank until `nvidia-drm` takes over (`README.md:187-224`). With the iGPU driving the monitor, the 4060 Ti can be a pure compute card and that hazard disappears. Cost: a reboot per session, plus an unsigned module in the initramfs that needs DKMS rebuilds (and signing, or Secure Boot stays off forever).

**What dual boot buys:** none of §5 changes. Linux removes ~0.5–1 GB of Windows desktop VRAM overhead, i.e. ~16k context at f16 KV instead of ~8k. That is all.

---

## 3. The "Windows port" — checked, and it does not cover this machine

`README.md:116` delegates Windows to **impacifist/Windows-GPU-UNLOCK** (1 216 stars, v0.3.1 "source-only pre-release"). It is not a port into Windows: it is a **UEFI DXE application that runs before Windows**, performs one unlock transaction, then chain-loads Windows Boot Manager without a reset.

What it requires (its `README.md` quick start): Secure Boot **off**, BitLocker off with C: fully decrypted, a **separate GPT FAT32 ESP ≥ 1 GiB** (its tools will not create, shrink or format partitions), a keyboard attached, Python 3.9+, clang/lld-link **20.1.8** exactly, five firmware assets obtained locally, admin PowerShell. Fixed-profile builds "compile for exactly one reviewed profile selected at build time in `internal-boot/unlock/machine-profile.h`".

Its `docs/COMPATIBILITY.en.md` lists **six exact machines**, every one Ampere — 3090 FE, 3090 Ti ×2, 3070 Ti, 3060 12 GB ×2. The local profile generator (`docs/NEW-MACHINE.en.md`) is the hard wall:

> "The generator refuses anything outside `research/profile/proven.json` … **There is no override flag.** Today that means:" RTX 3090/3090 Ti (`220410de`/`220310de`), RTX 3060 12 GB (`248710de`/`250410de`), RTX 3070 8 GB (`248410de`) — with coupled chip/VRAM tuples and a per-board PROM hash. It "does **not** add hardware support."

Three further structural mismatches here: (a) it wants "the RTX owns the only physical GOP", but the AMD iGPU is the console/display adapter on this box; (b) the existing ESP is 300 MiB and the tools will not resize it; (c) the board is a **Gigabyte** B650M, not the ASUS TUF B650M-PLUS of the only 7800X3D profile. Its scope table: "Other NVIDIA models/architectures — **Separate GPU port and validation required**".

**Net: the Windows path is closed today.** Its evidence is still useful: profile `b660m-3070ti` ran on **NVIDIA 616.92** — this machine's exact driver — and measured **FP16 88.7 / BF16 88.6 TFLOPS** against a locked baseline of ~43.7 on a 290 W 48-SM GA104. That single datapoint pins the model in §5.2.

---

## 4. Is the 4060 Ti really supported? Yes in the table, no in the evidence

- `kernel/gpu_unlock/recipes.c:411-412`: `/* AD106: RTX 4060 Ti, RTX 4060 Ti 16GB */` followed by `AD106(0x2803), AD106(0x2805),`. `10DE:2803` is the 8 GB card. `AD106` maps to chip id **0x196** (`recipes.c:374`), family `ad10x` (`recipes.c:345-356`: privileged table `ad102_plm`, host writes `selectors`, firmware `ad102_fw`, booter `sec2_ad102`, `fwsec_version = 3`).
- The pre-driver path *enforces* the id: `((chip >> 20) & 0x1ff) != work->card->chip` against `PMC_BOOT_0` (`unlock_610.c:1617-1622`) — an AD106 reports `0x196` and matches; an AD102 would not.
- `README.md:27` lists 4060/4060 Ti as **"Experimental"**.

**What "Experimental" means concretely.** Ampere claims "100+ user reports" and a published GEMM table (`README.md:49-59`); Ada has neither. In the tree:

- Exactly **one** Ada booter asset ships: `GU_FW_BOOTER_AD102 "…/610.43.03/booter_load_ad102.bin"` (`recipes.h:14`), shared by AD102/AD103/AD104/**AD106**/AD107 through the single `ad10x` family. No per-chip booter, no per-chip signature image.
- Its gadget table was produced by **porting** GA102's chain "one-for-one through the fwmap" (`recipes.c:70-84`), and the port is explicitly not exact: "AD102 has no exact counterpart for that function (the fwmap's fuzzy 0x73ec match performs a different table read)", so the cleanup came from a different chain entirely (`0x7a02`/`0x31b5`/`0x771e`, marker `0x67b00001`).
- The Ada provenance is one third-party transaction: "records one successful RTX 4090 production-booter transaction. **A hardware repeat of the refactored path is still needed**" (`firmware/NOTICE.md`).
- No Ada-specific commit in the 37-commit history; last device-id commit is `bb1088b` "Add all GA102 and GA104 device ids based on user reports" (2026-10-21). Web coverage I could reach (Bing via proxy; DuckDuckGo HTML blocked, `api.github.com` rate-limited, TechPowerUp unparseable) is exclusively RTX 30-series — **no 4060 Ti success report surfaced**.

So AD106 is *encoded* in the tables, but the validation behind it is a GA102→AD102 offset port plus the assumption that all five AD1xx chips ship the same SEC2 booter image. If AD106's booter build differs, the six-write chain lands on the wrong instructions: best case a clean `-EIO` with the stock signature restored (`unlock_610.c:1647-1649`), worst case the card needs a power cycle before it enumerates normally again.

---

## 5. The numbers: quantized-GGUF LLM on 8 GB, before vs. after

### 5.1 Where the FLOPs actually go (this is the whole analysis)

The unlock doubles FP16/BF16/TF32 **MMA with FP32 accumulation**. Whether that helps an LLM depends on which compute type the framework asks cuBLAS for. In llama.cpp (`ggml-org/llama.cpp`, master):

```c
// ggml/src/ggml-cuda/ggml-cuda.cu:1679-1691
ggml_type compute_type = src0->type;
if (ggml_is_quantized(compute_type)) {
    compute_type = fast_fp16_hardware_available(cc) ? GGML_TYPE_F16 : GGML_TYPE_F32;
} else if (compute_type == GGML_TYPE_BF16 && !fast_bf16_hardware_available(cc)) {
    if (GGML_CUDA_CC_IS_NVIDIA(cc) && src1->ne[1] > 8) compute_type = GGML_TYPE_F32;
}
```

and the type traits that decide the cuBLAS mode (`ggml-cuda.cu:1423-1453`):

| ggml type | cuBLAS compute | Tensor-core path | Throttled on GeForce? |
| --- | --- | --- | --- |
| `F32` (`:1423`) | `CUBLAS_COMPUTE_32F` | F32 accumulate | yes |
| `BF16` (`:1437`) | `CUBLAS_COMPUTE_32F` | F32 accumulate | **yes** |
| `F16` (`:1451`) | `CUBLAS_COMPUTE_16F` | **F16 accumulate** | **no — already full rate** |

Dispatch is at `ggml-cuda.cu:1744-1750`. **A quantized GGUF therefore dequantises to F16 and runs FP16-accumulate GEMM — the already-full-rate path.** The other road, the int8 tensor-core MMQ kernels (`mmq.cu:382-426`: Q4_K/Q5_K/Q6_K/Q8_0/IQ*/MXFP4/NVFP4 all eligible on sm_89), accumulate in INT32 and are equally outside the throttle. This is exactly why the README's own table prints "llama.cpp / Ollama with quantized GGUF — **0–15 %**" (`README.md:74`) and "INT8, FP8 and INT4 models — **No change**" (`README.md:76`).

The only way to land on a throttled path at 8 GB is BF16 **weights** — an 8 B model in BF16 is ~16 GB, twice the card. `GGML_CUDA_CUBLAS_COMPUTE_TYPE=f32` would force it, but F32 compute means converting the weight matrix to F32: double the bytes read, trading a 2× tensor-rate gain for a 2× bandwidth loss on a bandwidth-starved card. Net negative.

### 5.2 Peak throughput of *this* card, locked vs. unlocked

Ada SM = 4 fourth-gen tensor cores × 512 FP16 FLOP/clk with FP32 accumulate (1024 with F16 accumulate). RTX 4060 Ti = 34 SM.

| Clock | Locked peak (F32-acc) | Unlocked peak (F32-acc) |
| --- | --- | --- |
| 2.535 GHz (marketing boost) | **88.3 TFLOPS** | 176.6 TFLOPS |
| 2.580 GHz (driver ceiling, measured) | **89.9 TFLOPS** | 179.7 TFLOPS |
| 2.750 GHz (typical sustained) | 95.7 TFLOPS | 191.5 TFLOPS |

Model check against measured hardware (all from the Windows port's `docs/COMPATIBILITY.en.md`, cuBLAS GEMM n=4096): 3070 Ti 48 SM × 512 × 1.77 GHz = 43.5 predicted vs **43.7 measured** (−0.5 %); 3090 Ti 84 × 512 × 1.86 = 80.0 predicted vs **81.0 measured** (−1.2 %); 4090 128 × 512 × 2.52 = 165.1 vs the README's **165 TFLOPS** (`README.md:59`). Good to ~1 %.

Two honesty caveats about the "after" column. This card's power limit is **185 W** (measured), and the README itself warns "The RTX 4090 runs out of power before it runs out of tensor cores" (`README.md:61-62`); the 3090 Ti reached only 150.2 of a modelled 160.0 (94 % of the theoretical 2×). Expect **+80–95 %** sustained, not +100 %. And **none of it applies to the workload in question**, per §5.1.

### 5.3 The workload — 8 GB, 288 GB/s

Decode is bandwidth-bound: one token ≈ one pass over the weight file. Roofline at 288 GB/s peak, realistic 85 % achievement (245 GB/s):

| Model (Q4_K_M) | Weights | Bytes/token @ ctx | Roofline | Realistic decode | Prefill (int8 MMA, ~20 % of 176 TOPS) |
| --- | --- | --- | --- | --- | --- |
| Llama-3.1-8B | 4.92 GB | 4.92 GB @ 0 | 58.5 tok/s | **45–50 tok/s** | 1 800–2 600 tok/s |
| Llama-3.1-8B @ 8k ctx | 4.92 GB | 5.99 GB (f16 KV) | 48.1 | **~41 tok/s** | — |
| Qwen2.5-7B | 4.68 GB | 4.68 GB @ 0 | 61.5 | **47–52 tok/s** | 1 900–2 700 tok/s |
| Qwen3-8B (8.2 B) | 5.03 GB | 5.03 GB @ 0 | 57.3 | **44–49 tok/s** | 1 800–2 600 tok/s |
| Qwen2.5-14B | 8.99 GB | does not fit | — | **8–12 tok/s** (partial offload) | — |
| Gemma-3-12B | 7.3 GB | 7.3 GB @ 2–4k | 39.5 | **24–28 tok/s** | 1 200–1 800 tok/s |

Context budget from 8 188 MiB: −124 MiB measured desktop/chat-app overhead (more with OBS capturing), −250–400 MiB CUDA context, −300–500 MiB compute buffers ⇒ **≈ 6.6–7.4 GB usable for weights + KV**. KV for an 8 B / 32-layer / 8-KV-head / 128-dim model = 131 KB/token at f16 (65 KB at Q8_0):

- 8 B Q4_K_M + **8k** f16 KV = 5.99 GB → comfortable;
- 8 B Q4_K_M + **16k** Q8_0 KV = 5.99 GB → fits; 16k f16 KV = 7.06 GB → tight, OBS must idle;
- 8 B at **32k** → 8.1 GB of weights+KV alone: **no**.

### 5.4 Before vs. after, this machine

| Workload | Before (locked) | After (unlock) | Δ |
| --- | --- | --- | --- |
| Llama-3.1-8B / Qwen3-8B Q4_K_M, decode | ~41–50 tok/s | identical (bandwidth-bound) | **0 %** |
| same, prefill / TTFT (4k prompt) | ~1 800–2 600 tok/s (≈1.6–2.2 s) | identical (F16 or INT8 accumulate, unthrottled) | **0 %** |
| max context at 8 B Q4_K_M | 8k f16 / 16k Q8 KV | identical — VRAM unchanged | **0** |
| 14 B–32 B models | do not fit | do not fit | — |
| README's own llama.cpp row | — | "0–15 %, mostly at long context" (`README.md:74`) | ≈0 |
| SDXL / Flux image gen (bf16, F32-acc) | baseline | **+30–55 %** | real |
| BF16 LoRA fine-tune (small model) | baseline | **+25–50 %** | real, but 8 GB starves it |

The 0–15 % band is consistent with the attention/FlashAttention share of a long-context forward pass — an Amdahl artifact, not a matmul effect. It is not a reason to boot another OS. **The unlock's benefit for the stated goal is zero, and its ceiling — even if every README number held for AD106 — is 15 % on a workload that is bound by 288 GB/s and 8 GB.**

If more tok/s is the goal, the levers that move this machine are: 4-bit quant instead of 6/8 bit (≈2×), keeping the model under ~7 GB so nothing spills to the Ryzen side, a shorter context, and Q8_0 KV cache to buy context. The 7800X3D's iGPU (RDNA2, 2 CU) is not a fallback: at ~60–70 GB/s of shared DDR5 it would run the same 8 B model at single-digit tok/s.

---

## 6. Risks and costs

1. **It is a firmware-authentication bypass, not a tuning knob.** The module patches a signed SEC2 Booter, patches the FWSEC-FRTS blob from the VBIOS, and re-points the WPR2 metadata's signature fields at its own buffer (`unlock_610.c:1125-1154`, `vbios_610.c:341-375`). Legal exposure (NVIDIA EULA reverse-engineering clauses, DMCA §1201) is a real consideration for a work machine, not just a warranty question.
2. **It must run before the driver, every cold boot, from initramfs.** A bug there is a boot-time panic; recovery needs a kernel-command-line edit or a second GPU. This box's iGPU makes recovery practical — a genuine point in favour.
3. **Driver version is not actually irrelevant.** `README.md:120` says the pinned `610.43.03` is only used to extract firmware, and the module does ship its own booter blobs (`recipes.h:6-21`) — but the handover gates are transcribed from specific driver internals (`unlock_610.c:1557-1560` cites "both 610 and installed 615"), and **616.92 is not among them**. The Windows port's only 616.92 datapoint is an Ampere card.
4. **Failure modes are ugly.** If the firmware does not halt after the transaction, the module keeps its DMA buffers and a module reference "until power off" (`unlock_610.c` unwind path) — the card is effectively gone until the machine is powered down.
5. **"Outputs are bit-identical before and after" (`README.md:79`) is an assertion, not a test.** `tests/` contains one thing: `tests/docker.sh`, a CI script that builds the module and packages in containers (Debian 12/13, Ubuntu 22.04/24.04/26.04, Fedora, Arch). No numerical-correctness test, no hardware test, no golden output. You are trusting the argument, not a measurement.
6. **Documentation gap at the centre of gravity.** The firmware provenance note calls the new hardware path unvalidated and points at `docs/STAGE1.md` (`firmware/README.md:17`); that file is absent. 12.7 k stars, 37 commits, one 193-line design doc.
7. **Sleep/wake.** Linux: the module re-unlocks on resume through a PM notifier (~1 s, `main.c:117-127`); hibernate uncovered. Windows port: "S3 sleep invalidates the unlock … there is no resume path".
8. **Thermals/power are the least of the problems.** Standard throttling stays intact (`README.md:122-124`); the card sits at 185 W with 25 W idle, measured.

---

## 7. Recommendation

**Do not deploy this to get a local LLM.** Concretely:

- For the user's question — "which model, what context, what tok/s before vs after" — the honest answer: **Llama-3.1-8B-Instruct or Qwen3-8B at Q4_K_M, 8k context (16k with Q8_0 KV), ~41–50 tok/s decode and ~1 800–2 600 tok/s prefill, and the same numbers before and after the unlock.** The card's 288 GB/s and 8 GB are the ceiling; the unlock moves neither, and the quantized-GEMM path it would have to accelerate already runs at full rate (`ggml-cuda.cu:1679-1691`, `:1451`).
- The unlock is genuinely interesting for **BF16 LoRA fine-tuning** and **image generation**, where the F32-accumulate MMA path *is* used — but both need VRAM this card lacks. Buying VRAM is the cheaper, reversible way to buy capability than a dual boot with an unsigned kernel module.
- Of the three platform paths: **Windows native — impossible** (Linux kernel module); **WSL2 — impossible** (no BAR0, no PCI device, no FLR behind `/dev/dxg`); **the Windows UEFI port — closed for this machine** (no AD106 in `proven.json`, no override flag, no Ada hardware evidence, RTX does not own the GOP, ESP too small). **Dual boot Linux is the only route**, it fits this box best precisely because the monitor is on the iGPU, and it would buy **0 %** on the LLM workload.
- If the user wants it anyway for image-gen / fine-tuning: dual boot a distro with kernel ≥ 6.0 (needed for `aperture_remove_conflicting_pci_devices`, `unlock_610.c:1492-1495`), keep Secure Boot off, keep the monitor on the iGPU, and treat every `dmesg` line as either `stage=publish … ss0=0x88888888 ss1=0x8` (good) or a power cycle (bad). Budget an evening, and expect the AD106 transaction to be the first ever attempted on this chip class.

---

## Appendix — derivations and refuted premises

- **Peak tensor rates** from the Ada microarchitecture (4 TC/SM × 512 FP16 FLOP/clk with F32 accumulate, 1024 with F16 accumulate) × 34 SM × clock; cross-validated to ~1 % against three independently measured cards (§5.2).
- **Decode** from the bandwidth roofline `t = bytes_moved / 288 GB/s` at 85 % efficiency; KV bytes per token = `2 × n_layers × n_kv_heads × head_dim × bytes` (131 KB/token for an 8 B Llama-3-class model at f16). These are modelled, not measured here: no llama.cpp/Ollama is installed on this machine (`torch`, `ollama`, `nvcc` all absent). The before/after *delta* does not depend on the absolute values.
- **Host facts** measured on the machine (§2).
- **Refuted premise:** the brief's assumption that the 4060 Ti is the display output is wrong here — `nvidia-smi` reports `display_active = Disabled` and the AMD Radeon iGPU drives 2560×1440. That removes the screen-blanking hazard, and conversely breaks the Windows port's "RTX owns the GOP" precondition.
