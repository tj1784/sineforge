---
license: apache-2.0
tags:
- video-generation
- multi-reference
- LTX-2.3
base_model:
- Lightricks/LTX-2.3
github: https://github.com/liconstudio/ComfyUI-Licon-MSR
library_name: diffusers
---

# Licon MSR V2 for LTX-2.3

## What's New in V2

Compared with V1, **Licon MSR V2** introduces significant improvements in three key areas:

### 1. Improved Consistency

- Better preservation of character identity, clothing, objects, and scene details
- More consistent appearance across frames
- Improved alignment between multiple reference images and the generated video
- Reduced identity drift and reference attribute loss

### 2. Improved Stability

- More reliable results across repeated sampling runs
- Reduced visual artifacts, flickering, and temporal inconsistencies
- More stable generation in complex multi-subject compositions
- Improved handling of motion and interactions between subjects

### 3. Improved Scene Logic

- Better understanding of spatial and action relationships described in prompts
- More natural subject positioning and interaction
- Improved temporal progression from the beginning to the end of a video
- More coherent composition of characters, objects, and backgrounds

## Overview

This model implements a novel approach to multi-reference video generation using **Multiple Subject Reference (MSR)**. Instead of introducing additional encoder branches or fusion modules, we transform multiple static reference images into a pseudo-video sequence that shares the same representation space as the target video.

## Usage

This LoRA requires the **[ComfyUI-Licon-MSR](https://github.com/liconstudio/ComfyUI-Licon-MSR)** plugin for ComfyUI. A sample workflow is included in the model files for easy testing and experimentation.

## Key Features

### Multi-Reference Visual Memory

- **Token-level reference preservation**: Multiple reference images are encoded as video latents, preserving fine-grained visual information at the token level instead of compressing them into a single embedding
- **Native self-attention retrieval**: Target video tokens directly access reference tokens through the model's existing self-attention mechanism, with no additional architectural components required
- **In-context conditioning**: References serve as visual memory within the main token sequence rather than as external conditioning inputs

### Flexible Reference Composition

- **2 to 5 reference images**: Supports varying numbers of reference inputs with increasing composition complexity
- **Complementary semantic roles**: Each reference image can provide different information:
  - Subject identity
  - Object or prop details
  - Scene or background
  - Local textures
  - Multiple viewpoints

## What It Can Do

### Identity Preservation Across References

Generate videos in which multiple reference identities are simultaneously preserved:

- Multiple characters from different reference images
- Character and object combinations
- Object and scene compositions

### Relation-Based Composition

Beyond identity preservation, the model can compose references according to textual relationship descriptions:

- Action interactions, such as handing, picking up, or pushing
- Spatial relationships, such as left and right or foreground and background
- Temporal event structures, such as start → process → result

### Cross-Reference Attribute Selection

The model learns to selectively retrieve attributes from different references:

- Face from reference A and clothing from reference B
- Object identity from one reference and pose or position from another
- Background elements from scene references

## Usage Tips

- **Prompt description**: Use concise but accurate descriptions of the reference images. Both excessive and insufficient descriptions may reduce consistency.
- **Reference roles**: Clearly describe the role of each referenced subject, object, or scene in the target video.
- **High-motion scenes**: 50 fps is recommended for smoother motion coherence.
- **Sampling**: Complex multi-subject interactions may still benefit from multiple sampling runs.

## V1 vs. V2 Comparison

### Comparison 1

| V1 | V2 |
|:---:|:---:|
| [▶ Play V1](Validition_V2/01/V1_1.mp4) | [▶ Play V2](Validition_V2/01/V2.mp4) |

### Comparison 2

| V1 | V2 |
|:---:|:---:|
| [▶ Play V1](Validition_V2/02/V1.mp4) | [▶ Play V2](Validition_V2/02/V2.mp4)
