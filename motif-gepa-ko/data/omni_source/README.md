# English Omni-MATH source

`test.jsonl` is the original English [KbsdJames/Omni-MATH](https://huggingface.co/datasets/KbsdJames/Omni-MATH) test file (Apache-2.0), downloaded on 2026-09-27 from:

`https://huggingface.co/datasets/KbsdJames/Omni-MATH/resolve/main/test.jsonl`

SHA-256: `7c87be8ee41ac7c7a597ef5a5500e84bd2b639a85a06db3da7f69bf9a32ef168`.
The Apache-2.0 text is copied in [LICENSE-APACHE-2.0.txt](LICENSE-APACHE-2.0.txt).

The HRM8K Korean subset contains the original English problem text. `scripts/prepare_omni_v2.py` matches that exact text against this source to attach English reference solutions. The 16 cleaned HRM8K questions with more than one matching original row are placed in the v2 test split; their reference solutions are never used for training feedback.
