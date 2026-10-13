import { useEffect, useState } from 'react'

import AuthStatusBanner from './components/AuthStatusBanner'
import EventReviewTable from './components/EventReviewTable'
import SignInNotice from './components/SignInNotice'
import UploadForm from './components/UploadForm'
import { readSignInResult, readUploadId, withUploadId, withoutSignInParams } from './url'

export default function App() {
  // Read the URL once, on first render. These initialisers only read - no side effects -
  // because React's StrictMode may call them twice in development.
  const [signInResult] = useState(() => readSignInResult(window.location.search))
  const [uploadId, setUploadId] = useState(() => readUploadId(window.location.search))

  // Keep the URL in step with the page: drop the one-off sign-in message and remember which
  // upload is on screen, so a refresh doesn't lose it. replaceState (not pushState) means the
  // Back button isn't filled with old uploads, and running it twice is harmless.
  useEffect(() => {
    const search = withUploadId(withoutSignInParams(window.location.search), uploadId)
    window.history.replaceState(null, '', `${window.location.pathname}${search}`)
  }, [uploadId])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-4 py-4">
          <h1 className="text-xl font-semibold">Syllabus2Cal</h1>
          <AuthStatusBanner />
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
        <SignInNotice result={signInResult} />
        <UploadForm onUploaded={(upload) => setUploadId(upload.id)} />
        {uploadId !== null && <EventReviewTable uploadId={uploadId} />}
      </main>
    </div>
  )
}
