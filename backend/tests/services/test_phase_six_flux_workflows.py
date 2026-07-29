from backend.app.services.phase_six_images import _fallback_workflow


def test_flux1_fallback_uses_installed_dev_stack() -> None:
    workflow = _fallback_workflow(
        "Daniel leaves work",
        "identity drift",
        42,
        "cineforge/test",
        model_name="flux_dev.safetensors",
    )

    assert workflow["1"]["inputs"]["unet_name"] == "flux_dev.safetensors"
    assert workflow["2"]["class_type"] == "DualCLIPLoader"
    assert workflow["2"]["inputs"] == {
        "clip_name1": "clip_l.safetensors",
        "clip_name2": "t5xxl_fp16.safetensors",
        "type": "flux",
    }
    assert workflow["3"]["inputs"]["vae_name"] == "ae.safetensors"
    assert workflow["8"]["class_type"] == "KSampler"
    assert workflow["10"]["class_type"] == "SaveImage"


def test_flux2_fallback_keeps_flux2_spine() -> None:
    workflow = _fallback_workflow(
        "Daniel leaves work",
        "identity drift",
        42,
        "cineforge/test",
        model_name="Flux.2 Klein\\9B\\flux2Klein_9b.safetensors",
    )

    assert workflow["2"]["class_type"] == "CLIPLoader"
    assert workflow["11"]["class_type"] == "Flux2Scheduler"
    assert workflow["15"]["class_type"] == "SaveImage"
