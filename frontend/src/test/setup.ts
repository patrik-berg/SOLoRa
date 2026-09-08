import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)

// jsdom has dialog elements but not native top-layer/focus behavior.
HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) { this.open = true }
HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) { this.open = false }
