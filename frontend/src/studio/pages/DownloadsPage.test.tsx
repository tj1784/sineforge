import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { DownloadsPage } from './DownloadsPage'

afterEach(cleanup)

describe('DownloadsPage installation truth', () => {
  it('shows deleted 10Eros as missing and completed Sulphur GGUF assets as installed', () => {
    render(<DownloadsPage />)

    const erosLink = screen.getByRole('link', { name: 'LTX2.3 10Eros' })
    const erosRow = erosLink.closest('tr')
    expect(erosRow).not.toBeNull()
    expect(within(erosRow as HTMLTableRowElement).getByText('Missing')).toBeTruthy()
    expect(erosRow?.textContent).not.toContain('Installed')
    expect(erosRow?.textContent).toContain('Operator deleted')

    const sulphurLink = screen.getByRole('link', { name: 'Sulphur 2 Base Quants' })
    expect(sulphurLink.getAttribute('href')).toBe(
      'https://civitai.red/models/2630742/sulphur-2-base-quants?modelVersionId=2953675',
    )
    const sulphurRow = sulphurLink.closest('tr')
    expect(sulphurRow).not.toBeNull()
    const sulphurText = sulphurRow?.textContent ?? ''
    expect(sulphurText).toContain('Dev — official FP8 mixed quant')
    expect(sulphurText).toContain('LTXV 2.3')
    expect(sulphurText).toContain('None documented (no trigger word)')
    expect(sulphurText).toContain(
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\checkpoints\\LTX 2.3\\Sulphur 2\\sulphur2BaseQuants_dev.safetensors',
    )
    expect(sulphurText).toContain('41C999575859…')
    expect(within(sulphurRow as HTMLTableRowElement).getByText('Installed')).toBeTruthy()

    const rebelsWorkflowLink = screen.getByRole('link', {
      name: 'Rebels Sulphur 2 GGUF (LTX-2.3 NSFW Model)',
    })
    const rebelsWorkflowRow = rebelsWorkflowLink.closest('tr')
    expect(rebelsWorkflowRow).not.toBeNull()
    expect(rebelsWorkflowRow?.textContent).toContain('gguf')
    expect(rebelsWorkflowRow?.textContent).toContain('Sulphur_2_GGUF_LTX23.workflow.json')
    expect(within(rebelsWorkflowRow as HTMLTableRowElement).getByText('Installed')).toBeTruthy()

    const sulphurDistilRow = screen.getByRole('link', { name: 'Sulphur distil Q6_K GGUF' }).closest('tr')
    expect(sulphurDistilRow).not.toBeNull()
    expect(sulphurDistilRow?.textContent).toContain('C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\gguf\\sulphur_distil-Q6_K.gguf')
    expect(within(sulphurDistilRow as HTMLTableRowElement).getByText('Installed')).toBeTruthy()

    const rank768Row = screen.getByRole('link', { name: 'Sulphur rank-768 distillation LoRA' }).closest('tr')
    expect(rank768Row).not.toBeNull()
    expect(rank768Row?.textContent).toContain('sulphur_lora_rank_768.safetensors')
    expect(within(rank768Row as HTMLTableRowElement).getByText('Installed')).toBeTruthy()

    const videoVaeRow = screen.getByRole('link', { name: 'LTX 2.3 22B distilled video VAE' }).closest('tr')
    expect(videoVaeRow).not.toBeNull()
    expect(videoVaeRow?.textContent).toContain('ltx-2.3-22b-distilled_video_vae.safetensors')
    expect(within(videoVaeRow as HTMLTableRowElement).getByText('Installed')).toBeTruthy()

    for (const name of [
      'LTX 2.3 Ingredients IC-LoRA',
      'LTX 2.3 DubIt Lip-Sync IC-LoRA',
      'LTX 2.3 Pixel Spatial Upscaler IC-LoRA — 2×',
      'LTX 2.3 Pixel Spatial Upscaler IC-LoRA — 4×',
      'LTX 2.3 HDR IC-LoRA',
      'LTX 2.3 HDR Scene Embedding',
      'LTX 2.3 In/Outpainting IC-LoRA',
    ]) {
      const row = screen.getByRole('link', { name }).closest('tr')
      expect(row).not.toBeNull()
      expect(within(row as HTMLTableRowElement).getByText('Installed')).toBeTruthy()
      expect(row?.textContent).toContain('LTX 2.3')
    }

    const summary = screen.getByText('Download rows').closest('.workflow-summary')
    expect(summary).not.toBeNull()
    const summaryScope = within(summary as HTMLElement)
    expect(summaryScope.getByText('Download rows').parentElement?.textContent).toBe('Download rows37')
    expect(summaryScope.getByText('Installed / verified').parentElement?.textContent).toBe('Installed / verified34')
    expect(summaryScope.getByText('Missing').parentElement?.textContent).toBe('Missing3')
    expect(summaryScope.getByText('Downloading').parentElement?.textContent).toBe('Downloading0')
  })

  it('shows the IPAdapter runtime model install state separately', () => {
    render(<DownloadsPage />)

    const heading = screen.getByRole('heading', { name: 'IPAdapter runtime models' })
    const section = heading.closest('section')
    expect(section).not.toBeNull()
    expect(section?.textContent).toContain('Installed 15 of 32')
    expect(section?.textContent).toContain('17 remain pending')

    const vitHRow = screen.getByText('CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors').closest('tr')
    expect(vitHRow).not.toBeNull()
    expect(within(vitHRow as HTMLTableRowElement).getByText('Installed')).toBeTruthy()

    const bigGRow = screen.getByText('CLIP-ViT-bigG-14-laion2B-39B-b160k.safetensors').closest('tr')
    expect(bigGRow).not.toBeNull()
    expect(within(bigGRow as HTMLTableRowElement).getByText('Missing')).toBeTruthy()
    expect(bigGRow?.textContent).toContain('near-zero free space')
  })
})
