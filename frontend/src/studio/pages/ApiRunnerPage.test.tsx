import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../../api/client'
import { requestAppNavigation } from '../../navigationGuard'
import { ApiRunnerPage } from './ApiRunnerPage'

vi.mock('../../api/client', () => ({
  api: {
    listNativeApiRunnerWorkflows: vi.fn(),
    getNativeApiRunnerWorkflow: vi.fn(),
    createNativeApiRunnerWorkflow: vi.fn(),
    updateNativeApiRunnerWorkflow: vi.fn(),
    removeNativeApiRunnerWorkflow: vi.fn(),
    getNativeApiRunnerRuntime: vi.fn(),
    analyzeNativeApiRunnerWorkflow: vi.fn(),
    runNativeApiRunnerWorkflow: vi.fn(),
    getNativeApiRunnerJob: vi.fn(),
    cancelNativeApiRunnerJob: vi.fn(),
    freeNativeApiRunnerMemory: vi.fn(),
    uploadNativeApiRunnerMedia: vi.fn(),
    listApiCallerWorkflows: vi.fn(),
    importApiCallerRunnerWorkflows: vi.fn(),
    runApiCallerWorkflow: vi.fn(),
    listRuntimeWorkflowTemplates: vi.fn(),
  },
  nativeApiRunnerOutputUrl: (_promptId: string, output: { filename: string }) =>
    `http://native-output.test/${output.filename}`,
}))

const workflow = {
  '1': {
    class_type: 'TextNode',
    inputs: { text: 'A native test prompt', seed: 42 },
    _meta: { title: 'Positive prompt' },
  },
  '2': {
    class_type: 'SaveImage',
    inputs: { images: ['1', 0], filename_prefix: 'native/test' },
    _meta: { title: 'Save image' },
  },
}

const runtime = {
  schema: 'sineforge.native-api-runner/v1',
  ok: true,
  comfyUrl: 'http://127.0.0.1:8190',
  comfy: { status: 'ok', reachable: true },
  objectInfo: { available: true, classCount: 312, error: null },
  queue: {
    running: [],
    pending: [],
    runningCount: 0,
    pendingCount: 0,
  },
  externalRunnerUsed: false,
  capabilities: {
    library: true,
    liveValidation: true,
    directSubmission: true,
    mediaUpload: true,
    outputPreview: true,
    cancelPending: true,
    interruptActive: false,
    freeMemory: true,
    seedVariation: false,
    mergeMovie: false,
    saveLatents: false,
  },
}

const analysis = {
  schema: 'sineforge.native-api-runner/v1',
  ok: true,
  format: 'comfyui_api',
  queueable: true,
  workflowSha256: 'a'.repeat(64),
  nodeCount: 2,
  editable: [
    {
      nodeId: '1',
      classType: 'TextNode',
      title: 'Positive prompt',
      input: 'text',
      value: 'A native test prompt',
      valueType: 'str',
      label: '1 | Positive prompt | text',
    },
  ],
  mediaTargets: [],
  promptFields: [],
  outputNodes: [{ nodeId: '2', classType: 'SaveImage', title: 'Save image' }],
  modelRefs: [],
  issues: [],
  errorCount: 0,
  warningCount: 0,
}

function workflowDetail() {
  return {
    id: 'a5fa3f6a-a1e1-4639-945d-78f9a46cdab0',
    name: 'native-test',
    version: '1.0',
    description: 'Loaded from native-test.api.json',
    category: 'Uncategorized',
    subcategory: 'General',
    episode: null,
    instructions: null,
    tags: [],
    requirements: {},
    workflow_status: 'converted' as const,
    repository_managed: false,
    is_overridden: false,
    source_kind: 'native_operator_import',
    source_id: null,
    source_filename: 'native-test.api.json',
    source_archive: null,
    source_entry: null,
    node_count: 2,
    sha256: 'a'.repeat(64),
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-30T00:00:00Z',
    workflow,
    source_workflow: null,
    source_workflow_sha256: null,
  }
}

function repositoryWorkflowDetail() {
  return {
    ...workflowDetail(),
    repository_managed: true,
    source_kind: 'repository_import',
    source_archive: 'Ep07 Workflows.zip',
    source_entry: 'episode-07-workflow.json',
    source_workflow: {
      last_node_id: 2,
      last_link_id: 1,
      nodes: [
        { id: 1, type: 'TextNode', pos: [0, 0], size: [320, 120] },
        { id: 2, type: 'SaveImage', pos: [420, 0], size: [320, 120] },
      ],
      links: [[1, 1, 0, 2, 0, 'IMAGE']],
    },
    source_workflow_sha256: 'b'.repeat(64),
  }
}

beforeEach(() => {
  vi.mocked(api.listNativeApiRunnerWorkflows).mockResolvedValue([])
  vi.mocked(api.getNativeApiRunnerRuntime).mockResolvedValue(runtime as never)
  vi.mocked(api.analyzeNativeApiRunnerWorkflow).mockResolvedValue(analysis as never)
  vi.mocked(api.createNativeApiRunnerWorkflow).mockResolvedValue(workflowDetail() as never)
  vi.mocked(api.cancelNativeApiRunnerJob).mockResolvedValue({
    ok: true,
    promptId: 'prompt-native-1',
    action: 'interrupted_active',
  })
  vi.mocked(api.getNativeApiRunnerJob).mockResolvedValue({
    promptId: 'prompt-native-1',
    state: 'completed',
    completed: true,
    status: 'success',
    outputs: [],
    messages: [],
  })
  vi.mocked(api.runNativeApiRunnerWorkflow).mockResolvedValue({
    contract: 'sineforge.native-api-runner/v1',
    ok: true,
    prompt_id: 'prompt-native-1',
    queue_number: 1,
    client_id: 'sineforge-native-test',
    workflow_sha256: 'a'.repeat(64),
    submitted_at: '2026-07-30T00:00:00Z',
    external_runner_used: false,
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ApiRunnerPage native isolation', () => {
  it('starts with an empty library and never imports legacy Runner workflows', async () => {
    render(<ApiRunnerPage />)

    expect(await screen.findByRole('heading', { name: 'No workflows yet' })).toBeTruthy()
    expect(screen.getByText('Library is empty')).toBeTruthy()
    expect(screen.getByText(/repository workflows and operator-created entries/i)).toBeTruthy()
    expect(api.listNativeApiRunnerWorkflows).toHaveBeenCalledTimes(1)
    expect(api.listApiCallerWorkflows).not.toHaveBeenCalled()
    expect(api.importApiCallerRunnerWorkflows).not.toHaveBeenCalled()
    expect(api.listRuntimeWorkflowTemplates).not.toHaveBeenCalled()
    expect(api.analyzeNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.runNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.createNativeApiRunnerWorkflow).not.toHaveBeenCalled()
  })

  it('stages an operator JSON file, saves explicitly, validates, and submits natively', async () => {
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })

    const file = new File([JSON.stringify(workflow)], 'native-test.api.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })

    expect(await screen.findByRole('heading', { name: 'native test' })).toBeTruthy()
    expect(screen.getByDisplayValue('A native test prompt')).toBeTruthy()
    expect(api.createNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.runApiCallerWorkflow).not.toHaveBeenCalled()

    const runButton = screen.getByRole('button', { name: 'Run workflow' })
    expect((runButton as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('Validation required')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Save to library' }))
    await waitFor(() => expect(api.createNativeApiRunnerWorkflow).toHaveBeenCalledTimes(1))
    expect(api.createNativeApiRunnerWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'native test',
        source_filename: 'native-test.api.json',
        workflow,
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Validate live' }))
    await screen.findByText('Live validation passed')
    expect(api.analyzeNativeApiRunnerWorkflow).toHaveBeenCalledWith(workflow)
    expect((runButton as HTMLButtonElement).disabled).toBe(false)

    fireEvent.click(runButton)
    await waitFor(() => expect(api.runNativeApiRunnerWorkflow).toHaveBeenCalledTimes(1))
    expect(api.runNativeApiRunnerWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({
        workflow,
        workflow_name: 'native test',
        workflow_sha256: 'a'.repeat(64),
        confirmation: true,
      }),
    )
    expect(api.runApiCallerWorkflow).not.toHaveBeenCalled()
    expect(await screen.findByText('prompt-native-1')).toBeTruthy()
  })

  it('invalidates live validation after a rendered input edit', async () => {
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File([JSON.stringify(workflow)], 'native-test.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')

    fireEvent.click(screen.getByRole('button', { name: 'Validate live' }))
    await screen.findByText('Live validation passed')
    const runButton = screen.getByRole('button', { name: 'Run workflow' }) as HTMLButtonElement
    expect(runButton.disabled).toBe(false)

    fireEvent.change(screen.getByDisplayValue('A native test prompt'), {
      target: { value: 'Edited after validation' },
    })

    expect(runButton.disabled).toBe(true)
    expect(screen.getByText('Validation required')).toBeTruthy()
    expect(api.runNativeApiRunnerWorkflow).not.toHaveBeenCalled()
  })

  it('keeps execution blocked while the local engine is offline or validation is not queueable', async () => {
    vi.mocked(api.getNativeApiRunnerRuntime).mockResolvedValueOnce({
      ...runtime,
      ok: false,
      comfy: { status: 'unavailable', reachable: false },
    } as never)
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File([JSON.stringify(workflow)], 'native-test.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')

    expect((screen.getByRole('button', { name: 'Validate live' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Run workflow' }) as HTMLButtonElement).disabled).toBe(true)

    cleanup()
    vi.mocked(api.getNativeApiRunnerRuntime).mockResolvedValue(runtime as never)
    vi.mocked(api.analyzeNativeApiRunnerWorkflow).mockResolvedValueOnce({
      ...analysis,
      ok: false,
      queueable: false,
      issues: [
        {
          severity: 'error',
          code: 'missing_node',
          message: 'A required node is unavailable.',
          nodeId: '1',
          input: null,
        },
      ],
      errorCount: 1,
    } as never)
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const secondFileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(secondFileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')
    fireEvent.click(screen.getByRole('button', { name: 'Validate live' }))

    expect(await screen.findByText('1 run issue')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Run workflow' }) as HTMLButtonElement).disabled).toBe(true)
    expect(api.runNativeApiRunnerWorkflow).not.toHaveBeenCalled()
  })

  it('uses raw JSON edits directly for saving, downloading, and leaving the raw editor', async () => {
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File([JSON.stringify(workflow)], 'native-test.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')

    fireEvent.click(screen.getByRole('button', { name: 'Raw API JSON' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Raw API workflow JSON' }), {
      target: {
        value: JSON.stringify({
          ...workflow,
          '1': {
            ...workflow['1'],
            inputs: { ...workflow['1'].inputs, text: 'Edited in raw JSON' },
          },
        }),
      },
    })

    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: 'Save to library' }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    )
    expect(
      (screen.getByRole('button', { name: 'Download JSON' }) as HTMLButtonElement).disabled,
    ).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Editable inputs' }))
    expect(screen.getByDisplayValue('Edited in raw JSON')).toBeTruthy()
  })

  it('preserves a newer rendered-input edit when an earlier save response arrives', async () => {
    let resolveSave: ((value: ReturnType<typeof workflowDetail>) => void) | undefined
    vi.mocked(api.createNativeApiRunnerWorkflow).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSave = resolve
        }),
    )

    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File([JSON.stringify(workflow)], 'native-test.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')

    fireEvent.click(screen.getByRole('button', { name: 'Save to library' }))
    await waitFor(() => expect(api.createNativeApiRunnerWorkflow).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByDisplayValue('A native test prompt'), {
      target: { value: 'A newer unsaved prompt' },
    })

    expect(resolveSave).toBeTypeOf('function')
    await act(async () => {
      resolveSave?.(workflowDetail())
    })

    expect(await screen.findByText(/newer local edits remain unsaved/i)).toBeTruthy()
    expect(screen.getByDisplayValue('A newer unsaved prompt')).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: 'Save workflow' }) as HTMLButtonElement).disabled,
    ).toBe(false)
    expect(api.createNativeApiRunnerWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({
        workflow,
      }),
    )
  })

  it('guards dirty drafts before replacing them or leaving through SPA navigation', async () => {
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File([JSON.stringify(workflow)], 'native-test.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')

    fireEvent.click(screen.getAllByRole('button', { name: 'Paste JSON' })[0])
    expect(await screen.findByRole('heading', { name: 'Discard the current working copy?' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Paste API workflow JSON' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }))

    let navigated = false
    expect(requestAppNavigation(() => {
      navigated = true
    })).toBe(false)
    expect(await screen.findByRole('heading', { name: 'Discard the current working copy?' })).toBeTruthy()
    expect(navigated).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Discard & continue' }))
    expect(navigated).toBe(true)
  })

  it('reuses the same run idempotency key after an ambiguous submission failure', async () => {
    vi.mocked(api.runNativeApiRunnerWorkflow)
      .mockRejectedValueOnce(new Error('Connection closed after submission'))
      .mockResolvedValueOnce({
        contract: 'sineforge.native-api-runner/v1',
        ok: true,
        prompt_id: 'prompt-native-1',
        queue_number: 1,
        client_id: 'sineforge-native-test',
        workflow_sha256: 'a'.repeat(64),
        submitted_at: '2026-07-30T00:00:00Z',
        external_runner_used: false,
      })
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File([JSON.stringify(workflow)], 'native-test.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')
    fireEvent.click(screen.getByRole('button', { name: 'Validate live' }))
    await screen.findByText('Live validation passed')

    const runButton = screen.getByRole('button', { name: 'Run workflow' })
    fireEvent.click(runButton)
    expect(await screen.findByText('Connection closed after submission')).toBeTruthy()
    fireEvent.click(runButton)
    await waitFor(() => expect(api.runNativeApiRunnerWorkflow).toHaveBeenCalledTimes(2))

    const firstPayload = vi.mocked(api.runNativeApiRunnerWorkflow).mock.calls[0][0]
    const secondPayload = vi.mocked(api.runNativeApiRunnerWorkflow).mock.calls[1][0]
    expect(secondPayload.idempotency_key).toBe(firstPayload.idempotency_key)
  })

  it('requires confirmation before stopping a Sineforge-owned running prompt', async () => {
    vi.mocked(api.getNativeApiRunnerRuntime).mockResolvedValue({
      ...runtime,
      capabilities: {
        ...runtime.capabilities,
        interruptActive: true,
      },
    } as never)
    vi.mocked(api.getNativeApiRunnerJob).mockResolvedValue({
      promptId: 'prompt-native-1',
      state: 'running',
      completed: false,
      status: 'executing',
      outputs: [],
      messages: [],
    })
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File([JSON.stringify(workflow)], 'native-test.json', {
      type: 'application/json',
    })
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })
    await screen.findByDisplayValue('A native test prompt')
    fireEvent.click(screen.getByRole('button', { name: 'Validate live' }))
    await screen.findByText('Live validation passed')
    fireEvent.click(screen.getByRole('button', { name: 'Run workflow' }))

    const stopButton = await screen.findByRole('button', { name: 'Stop' })
    fireEvent.click(stopButton)
    expect(await screen.findByRole('heading', { name: 'Stop native test?' })).toBeTruthy()
    expect(screen.getByText(/submitted by the Sineforge native Runner/i)).toBeTruthy()
    expect(api.cancelNativeApiRunnerJob).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Stop running prompt' }))
    await waitFor(() =>
      expect(api.cancelNativeApiRunnerJob).toHaveBeenCalledWith('prompt-native-1', true),
    )
    expect(await screen.findByText('Interrupted active prompt prompt-native-1.')).toBeTruthy()
  })

  it('rejects visual-format JSON without saving or falling back to the external Runner', async () => {
    render(<ApiRunnerPage />)
    await screen.findByRole('heading', { name: 'No workflows yet' })
    const file = new File(
      [JSON.stringify({ nodes: [{ id: 1, type: 'KSampler' }], links: [] })],
      'visual-workflow.json',
      { type: 'application/json' },
    )
    const fileInput = document.querySelector('input[type="file"][accept*=".json"]')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } })

    expect(await screen.findByText(/Visual workflow JSON is not executable/i)).toBeTruthy()
    expect(api.createNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.analyzeNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.runNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.runApiCallerWorkflow).not.toHaveBeenCalled()
  })

  it('keeps repository originals protected and creates an editable Sineforge API copy', async () => {
    const repositoryWorkflow = repositoryWorkflowDetail()
    vi.mocked(api.listNativeApiRunnerWorkflows).mockResolvedValue([
      repositoryWorkflow,
    ] as never)
    vi.mocked(api.getNativeApiRunnerWorkflow).mockResolvedValue(
      repositoryWorkflow as never,
    )
    render(<ApiRunnerPage />)
    const libraryName = await screen.findByText(repositoryWorkflow.name)
    fireEvent.click(libraryName.closest('button') as HTMLButtonElement)

    expect(await screen.findByText('Protected repository workflow')).toBeTruthy()
    expect(screen.getByText('Read-only library')).toBeTruthy()
    expect(
      (screen.getByDisplayValue(repositoryWorkflow.name) as HTMLInputElement).readOnly,
    ).toBe(true)
    expect(
      (screen.getByDisplayValue('A native test prompt') as HTMLTextAreaElement).readOnly,
    ).toBe(true)
    expect(screen.queryByRole('button', { name: 'Archive' })).toBeNull()
    expect(
      (screen.getByRole('button', { name: 'Save workflow' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
    expect(screen.queryByRole('link', { name: /Load in ComfyUI/i })).toBeNull()
    expect(screen.getByText(/entirely inside Sineforge/i)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Save as copy' }))
    expect(
      (screen.getByDisplayValue('native-test copy') as HTMLInputElement).readOnly,
    ).toBe(false)
    expect(
      (screen.getByDisplayValue('A native test prompt') as HTMLTextAreaElement).readOnly,
    ).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Raw API JSON' }))
    const rawEditor = screen.getByRole('textbox', { name: 'Raw API workflow JSON' }) as HTMLTextAreaElement
    expect(rawEditor.readOnly).toBe(false)
    expect(rawEditor.value).toContain('A native test prompt')
    expect(screen.getByRole('button', { name: 'Save to library' })).toBeTruthy()

    expect(api.updateNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.removeNativeApiRunnerWorkflow).not.toHaveBeenCalled()
    expect(api.runNativeApiRunnerWorkflow).not.toHaveBeenCalled()
  })
})
