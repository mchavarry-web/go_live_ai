import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["menu"]

  toggle(event) {
    event.preventDefault()
    this.menuTarget.classList.toggle("hidden")
  }
}
