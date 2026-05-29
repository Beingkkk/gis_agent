import { Routes, Route } from 'react-router-dom'
import MainPage from './pages/MainPage'
import GeneratorPage from './pages/GeneratorPage'
import PipelinePage from './pages/PipelinePage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<MainPage />} />
      <Route path="/generator" element={<GeneratorPage />} />
      <Route path="/pipeline" element={<PipelinePage />} />
    </Routes>
  )
}

export default App
