export default function ExportButton({ kind, label }: { kind: "tickets" | "invoices" | "devices"; label: string }) {
  return (
    <a className="text-sm text-blue-700 hover:underline" href={`/api/v1/portal/export/${kind}.csv`} download>
      {label}
    </a>
  );
}
