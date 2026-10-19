import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { DemoApp } from './demo/DemoApp'
import './index.css'

const root = document.getElementById('root')
if (root !== null) createRoot(root).render(<StrictMode><DemoApp /></StrictMode>)
