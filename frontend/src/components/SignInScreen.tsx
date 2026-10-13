import { googleSignInUrl } from '../api/client'

/** What signed-out visitors see: what the app does, and a way in. */
export default function SignInScreen() {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-8 text-center">
      <h2 className="text-lg font-semibold">Turn a course schedule into calendar events</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">
        Upload a syllabus PDF, check the lectures, labs and deadlines it finds, then add them to your Google
        Calendar.
      </p>
      <a
        href={googleSignInUrl}
        className="mt-6 inline-block rounded-md bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
      >
        Sign in with Google
      </a>
      <p className="mt-3 text-xs text-slate-500">
        Google will also ask to let Syllabus2Cal add events to your calendar. It can't see your other events.
      </p>
    </section>
  )
}
