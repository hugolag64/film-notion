import BackstagePrototype from './BackstagePrototype'
import AuthGate from './AuthGate'

function App() {
  return (
    <AuthGate>
      <BackstagePrototype />
    </AuthGate>
  )
}

export default App
