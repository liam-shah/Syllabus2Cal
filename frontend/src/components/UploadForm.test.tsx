import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { makeUpload } from '../test/factories'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import UploadForm from './UploadForm'

const pdfFile = () => new File(['%PDF-1.7'], 'cpsc213.pdf', { type: 'application/pdf' })

describe('UploadForm', () => {
  it('only enables the button once a file is chosen', async () => {
    const user = userEvent.setup()
    renderWithQueryClient(<UploadForm onUploaded={vi.fn()} />)

    const button = screen.getByRole('button', { name: 'Extract events' })
    expect(button).toBeDisabled()

    await user.upload(screen.getByLabelText('PDF file'), pdfFile())
    expect(button).toBeEnabled()
  })

  it('shows progress while uploading, then hands the upload to the parent', async () => {
    const user = userEvent.setup()
    let respond!: (response: Response) => void
    const fetchMock = mockFetch(() => new Promise<Response>((resolve) => { respond = resolve }))
    const onUploaded = vi.fn()
    renderWithQueryClient(<UploadForm onUploaded={onUploaded} />)

    await user.upload(screen.getByLabelText('PDF file'), pdfFile())
    await user.click(screen.getByRole('button', { name: 'Extract events' }))

    // While the request is running there's no way to submit twice.
    expect(await screen.findByRole('button', { name: 'Uploading…' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const accepted = makeUpload({ status: 'processing' })
    respond(jsonResponse(accepted, 202))
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(accepted))
  })

  it("shows the backend's error message when the upload fails", async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse({ detail: 'Could not read the file as a PDF' }, 400))
    const onUploaded = vi.fn()
    renderWithQueryClient(<UploadForm onUploaded={onUploaded} />)

    await user.upload(screen.getByLabelText('PDF file'), pdfFile())
    await user.click(screen.getByRole('button', { name: 'Extract events' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not read the file as a PDF')
    expect(onUploaded).not.toHaveBeenCalled()
  })
})
