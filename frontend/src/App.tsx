import { Routes, Route } from 'react-router-dom'
import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react'
import { AppLayout } from './components/layout/AppLayout'
import { HomePage }    from './pages/Home'
import { ImportsPage }        from './pages/Imports'
import { CommercialQueuePage } from './pages/CommercialQueue'
import { MyDayPage }          from './pages/MyDay'
import { ClientCRMPage }      from './pages/ClientCRM'
import { ManagerViewPage }    from './pages/ManagerView'
import { UserAccessPage }     from './pages/UserAccess'
import { ClientsPage } from './pages/Clients'

export default function App() {
  return (
    <>
      <SignedIn>
        <AppLayout>
          <Routes>
            <Route path="/"        element={<HomePage />}   />
            <Route path="/imports" element={<ImportsPage />} />
            <Route path="/clients" element={<ClientsPage />}/>
                        <Route path="/commercial-queue" element={<CommercialQueuePage />} />
              <Route path="/my-day"           element={<MyDayPage />} />
              <Route path="/clients/:clientId" element={<ClientCRMPage />} />
              <Route path="/manager"           element={<ManagerViewPage />} />
              <Route path="/users"             element={<UserAccessPage />} />
            </Routes>
        </AppLayout>
      </SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </>
  )
}
