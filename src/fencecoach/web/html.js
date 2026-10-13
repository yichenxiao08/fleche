/**
 * Identity tag for HTML template literals.
 * It lets Prettier format embedded markup and drops formatting-only line breaks
 * between tags before the template is inserted into the page.
 */
export function html(strings, ...values) {
  return strings
    .reduce(
      (result, part, index) =>
        result + part + (index < values.length ? values[index] : ""),
      "",
    )
    .replace(/>\r?\n[ \t]*</g, "><");
}
