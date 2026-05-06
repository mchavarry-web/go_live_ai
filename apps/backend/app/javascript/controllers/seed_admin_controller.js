import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static values = { email: String, password: String }

  fill() {
    const form = this.element.closest("form")
    if (!form) return
    const email = form.querySelector('input[type="email"]')
    const password = form.querySelector('input[type="password"]')
    if (email) {
      email.value = this.emailValue
      email.dispatchEvent(new Event("input", { bubbles: true }))
    }
    if (password) {
      password.value = this.passwordValue
      password.dispatchEvent(new Event("input", { bubbles: true }))
    }
  }
}
