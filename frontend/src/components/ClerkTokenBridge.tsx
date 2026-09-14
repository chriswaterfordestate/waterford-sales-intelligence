/**
 * Bridges the Clerk React auth context into the standalone api.ts module.
 *
 * Why: apiRequest() in api.ts is a plain async function, not a React component.
 * It cannot call hooks directly. This component uses the official
 * @clerk/clerk-react useAuth() hook to obtain getToken(), then registers it
 * with the api.ts module-level token provider so all API calls attach the
 * real Clerk JWT.
 *
 * Mount exactly once, inside <ClerkProvider>, near the root of the component tree.
 * See App.tsx.
 */
import { useEffect } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { setClerkTokenProvider } from '../lib/api'

export function ClerkTokenBridge() {
  const { getToken } = useAuth()

  useEffect(() => {
    // Register the Clerk hook's getToken with the central API client.
    // getToken() returns a Promise<string | null> (null when signed out).
    setClerkTokenProvider(() => getToken())
  }, [getToken])

  return null  // renders nothing — auth infrastructure only
}
