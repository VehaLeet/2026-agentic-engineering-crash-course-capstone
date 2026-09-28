const kyiv = new Intl.DateTimeFormat('uk-UA', {
  timeZone: 'Europe/Kyiv',
  dateStyle: 'short',
  timeStyle: 'short',
})

/** Час за Києвом незалежно від часового поясу браузера — сервіс про український ринок. */
export function formatKyiv(iso: string): string {
  return kyiv.format(new Date(iso))
}
