import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["menu"]

  connect() {
    this.boundHideOnClickOutside = this.hideOnClickOutside.bind(this)
  }

  toggle(event) {
    event.stopPropagation()
    this.menuTarget.classList.toggle("hidden")

    if (!this.menuTarget.classList.contains("hidden")) {
      document.addEventListener("click", this.boundHideOnClickOutside)
    }
  }

  hide() {
    this.menuTarget.classList.add("hidden")
    document.removeEventListener("click", this.boundHideOnClickOutside)
  }

  hideOnClickOutside(event) {
    if (!this.element.contains(event.target)) {
      this.hide()
    }
  }

  disconnect() {
    document.removeEventListener("click", this.boundHideOnClickOutside)
  }
}
