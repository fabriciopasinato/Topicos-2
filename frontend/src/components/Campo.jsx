/** Campo de formulario con etiqueta y error asociado.
 *  El error queda FUERA del <label> (asi no se suma al nombre accesible del
 *  campo) y se vincula con aria-describedby. */
export default function Campo({ label, nombre, error, children, ...props }) {
  const idError = error ? `${nombre}-error` : undefined;
  return (
    <div className="campo">
      <label>
        {label}
        {children ?? (
          <input name={nombre} aria-invalid={Boolean(error)} aria-describedby={idError} {...props} />
        )}
      </label>
      {error && (
        <span id={idError} className="mensaje mensaje-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
