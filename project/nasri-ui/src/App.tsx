const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export default function App() {
  return (
    <main className="page">
      <section className="card">
        <p className="eyebrow">Nasri UI</p>
        <h1>Frontend hazır</h1>
        <p>
          Backend endpoint: <code>{API_BASE_URL}</code>
        </p>
        <p>İlk adım olarak bu projeye route, auth ve state katmanını ekleyebiliriz.</p>
      </section>
    </main>
  );
}
