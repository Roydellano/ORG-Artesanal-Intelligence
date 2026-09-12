/** Format integer centavos without inventing values for missing API fields. */
export function money(value: unknown, currency = "MXN"): string {
  if (
    !(typeof value === "number" && Number.isSafeInteger(value)) &&
    !(typeof value === "string" && /^-?\d+$/.test(value)) &&
    typeof value !== "bigint"
  ) {
    return "Unavailable";
  }
  const cents = BigInt(value as number | string | bigint);
  const magnitude = cents < 0n ? -cents : cents;
  return `${currency} ${cents < 0n ? "-" : ""}$${(magnitude / 100n).toLocaleString("en-US")}.${(magnitude % 100n).toString().padStart(2, "0")}`;
}
