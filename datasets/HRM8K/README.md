---
license: mit
configs:
- config_name: MATH
  data_files:
  - split: test
    path: HRM8K/math_do_test.csv
- config_name: GSM8K
  data_files:
  - split: test
    path: HRM8K/gsm8k_test.csv
- config_name: OMNI_MATH
  data_files:
  - split: test
    path: HRM8K/omni-math_do_test.csv
- config_name: MMMLU
  data_files:
  - split: test
    path: HRM8K/mmmlu_test.csv
- config_name: KSM
  data_files:
  - split: test
    path: HRM8K/ksm_test.csv
language:
- ko
- en
tags:
- haerae
---

<p align="center"><img src="https://framerusercontent.com/images/u6EoOFN42qJ1mYqfwF8uEsiKc.png?scale-down-to=1024&lossless=1" alt="HRM8K" width="300" height="300" /></p>

<p align="center">| 📖 <a href="https://www.arxiv.org/abs/2501.02448" target="_blank">Paper</a> | 📝 <a href="https://www.onelineai.com/blog/hrm8k" target="_blank">Blog</a> | 🖥️ Code(Coming soon!) |</p>

# HRM8K

We introduce **HAE-RAE Math 8K** (**HRM8K**), a bilingual math reasoning benchmark for Korean and English.
HRM8K comprises 8,011 instances for evaluation, sourced through a combination of translations from established English benchmarks (e.g., GSM8K, MATH, OmniMath, MMMLU) and original problems curated from existing Korean math exams.

## Benchmark Overview

The **HRM8K** benchmark consists of two subsets:

- **Korean School Math** (**KSM**): This subset comprises 1,428 challenging mathematical problems from Korean sources.
We collect only from Olympiad or competition-level exams, regardless of the target age group.
Consequently, even problems from younger curricula require a certain level of reasoning ability to solve.
The sources from which data was collected are as follows:
  - KMO (한국수학올림피아드)
  - KJMO (한국주니어수학올림피아드)
  - CSAT (대학수학능력시험)
  - KMS (한국대학수학경시대회)
  - TQ (교원임용경쟁시험)
- **Prior Sets**: This subset comprises 6,583 problems from existing English mathematics benchmarks.
We retain only instances with numeric answers for the Math and Omni-MATH datasets, excluding those with text, equations, or proofs as final answers.
In addition, we select only three math-related subsets, including `abstract_algebra`, `college_mathematics`, and `high_school_mathematics` from MMMLU datasets.
The sources from which data was collected are as follows:
  - [GSM8K](https://huggingface.co/datasets/openai/gsm8k)
  - [MATH](https://huggingface.co/datasets/hendrycks/competition_math)
  - [Omni-MATH](https://huggingface.co/datasets/KbsdJames/Omni-MATH)
  - [MMMLU](https://huggingface.co/datasets/openai/MMMLU)

## Benchmark Formulation

- **Translation**: To create a bilingual (English-Korean) dataset, we translate every instance in both **KSM** and **Prior Sets** using GPT-4o. 
Translated samples undergo human review, and inaccurate entries are removed.
- **OCR**: For the KSM dataset, we manually capture the problems as screenshots, process them through OCR using the GPT-4 API, and validate.

## Benchmark Contamination

To ensure that the **KSM** subset is not included in the pretraining corpora of LLMs, we perform a contamination check in the following steps:

1. Retrieve approximately 58 million Korean documents, totaling 95GB, from [FineWeb-2](HuggingFaceFW/fineweb-2).
3. Verify whether the sources used to construct **HRM8K** are present in retrieved documents, resulting in 149 matches over the 11-year period.
4. Examine these 149 documents for the presence of an exact match string from HRM8K, and we find no matches.

This is likely because, although we collect samples from online sources, none are directly crawled; 
the authors manually downloaded PDF or HWP files and extracted questions, making it challenging for automatic crawlers to collect them.

## Dataset Usage

```python
from datasets import load_dataset

data_category = ["GSM8K", "MATH", "OMNI_MATH", "MMMLU", "KSM"]   # The subests of HRM8K

# Load all subests
all_dataset = {cat: load_dataset('HAERAE-HUB/HRM8K', cat, split="test") for cat in data_category}

# Load one subest
dataset = load_dataset("HAERAE-HUB/HRM8K", subset, split="test")   # Change 'subset' to the desired subest
```

## Contributors

```
Hyunwoo Ko, Guijin Son, Dasol Choi
```

## Point of Contact

For any questions contact us via the following email :)

```
hyunwooko@onelineai.com, spthsrbwls123@yonsei.ac.kr, dasolchoi@yonsei.ac.kr
```