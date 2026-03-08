<svelte:head>
  <title>nasri | landing</title>
</svelte:head>

<main class="landing">
  <section class="center">
    <img src="/nasri-mark.svg" alt="Nasri" class="logo-mark" />
    <h1 class="wordmark">nasri</h1>
    <p class="tagline">Selamunaleyküm ben Nasrî</p>
  </section>
  <footer class="footer">Mart 2026 (v.0.0.0)</footer>
</main>

<style>
  :global(html, body) {
    margin: 0;
    min-height: 100%;
    background: #fff;
    color: #202226;
    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
  }

  .landing {
    min-height: 100dvh;
    display: grid;
    grid-template-rows: 1fr auto;
    place-items: center;
    padding: 16px;
  }

  .center {
    text-align: center;
  }

  .logo-mark {
    width: min(26vw, 120px);
    min-width: 72px;
    height: auto;
    opacity: 0.9;
  }

  .wordmark {
    margin: 10px 0 4px;
    font-weight: 600;
    letter-spacing: 0.03em;
    font-size: clamp(2.1rem, 7vw, 4rem);
    line-height: 1;
    color: #44474d;
  }

  .tagline {
    margin: 6px 0 0;
    font-size: 10pt;
    font-weight: 400;
    color: #50545d;
  }

  .footer {
    width: 100%;
    text-align: center;
    font-size: 8pt;
    font-style: italic;
    color: #666b75;
    padding-bottom: 10px;
  }
</style>

