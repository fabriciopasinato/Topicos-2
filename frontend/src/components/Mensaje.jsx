export default function Mensaje({ tipo = "error", children }) {
  if (!children) return null;
  return (
    <p role={tipo === "error" ? "alert" : "status"} className={`mensaje mensaje-${tipo}`}>
      {children}
    </p>
  );
}
