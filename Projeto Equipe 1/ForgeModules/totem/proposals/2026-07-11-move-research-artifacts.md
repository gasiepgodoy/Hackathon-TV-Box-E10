# Move Research Artifacts to Dedicated Directory

## Summary
Move the Jupyter Notebook `Mina_Intent_Classifier_Colab.ipynb` to a new `research/` or `notebooks/` directory to separate experimental artifacts from application source code.

## Problem
The root directory of the repository contains `Mina_Intent_Classifier_Colab.ipynb`. Jupyter notebooks are research and development artifacts, not production code. Having them in the root directory clutters the workspace and mixes application code with experimental models.

## Evidence
Running `ls -la` in the repository root reveals `Mina_Intent_Classifier_Colab.ipynb` alongside core application files like `main_cli.py`, `main_gui.py`, and `mabi_voice_interface.py`.

## Proposed Solution
Create a new directory named `research/` (or `notebooks/`) in the repository root. Move `Mina_Intent_Classifier_Colab.ipynb` into this directory. Update any documentation (like the README) that might reference the old path.

## Benefits
- **Cleanliness:** Keeps the repository root focused on application entry points.
- **Organization:** Establishes a dedicated space for future data science, model training, or research scripts without cluttering the core codebase.

## Trade-offs
- Links to the notebook in existing PRs or external documentation might break.

## Risks
- None, assuming the notebook is standalone and does not rely on a specific relative path to access other repository files (if it does, those paths will need adjustment).

## Estimated Complexity
- Low

## Priority
- Low

## Success Criteria
- `Mina_Intent_Classifier_Colab.ipynb` is no longer in the repository root.
- The notebook functions correctly in its new location.

## Open Questions
- Are there other training scripts or model evaluation artifacts that should also be moved into this new directory?
