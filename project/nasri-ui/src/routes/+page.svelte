<script lang="ts">
  import { onMount } from "svelte";
  import {
    fetchDevices,
    fetchHealthReady,
    fetchLogs,
    fetchMaintenanceStatus,
    sendChat,
    type ChatPayload,
    type HealthReady,
    type MaintenanceStatus,
    type NetworkDevice,
  } from "$lib/api";

  let health: HealthReady | null = null;
  let devices: NetworkDevice[] = [];
  let logs: string[] = [];
  let maintenance: MaintenanceStatus | null = null;
  let loading = true;
  let errors: string[] = [];

  let sessionId = "";
  let message = "";
  let replies: { role: "user" | "assistant"; text: string }[] = [];
  let sending = false;

  async function loadDashboard() {
    loading = true;
    errors = [];
    try {
      health = await fetchHealthReady();
    } catch (e) {
      errors.push(`health: ${String(e)}`);
    }
    try {
      devices = await fetchDevices();
    } catch (e) {
      errors.push(`devices: ${String(e)}`);
    }
    try {
      maintenance = await fetchMaintenanceStatus();
    } catch (e) {
      errors.push(`maintenance: ${String(e)}`);
    }
    try {
      logs = await fetchLogs(20);
    } catch (e) {
      errors.push(`logs: ${String(e)}`);
    }
    loading = false;
  }

  async function submitChat() {
    const text = message.trim();
    if (!text || sending) return;
    sending = true;
    replies = [...replies, { role: "user", text }];
    message = "";
    try {
      const data: ChatPayload = await sendChat(text, sessionId || undefined);
      sessionId = data.session_id;
      replies = [...replies, { role: "assistant", text: data.reply }];
    } catch (e) {
      replies = [...replies, { role: "assistant", text: `Hata: ${String(e)}` }];
    } finally {
      sending = false;
    }
  }

  onMount(loadDashboard);
</script>

<svelte:head>
  <title>nasri dashboard</title>
</svelte:head>

<main class="page">
  <header class="hero">
    <h1>Nasri Dashboard</h1>
    <p>sohbet, sistem durumu, cihazlar ve log akışı tek panelde</p>
    <button class="refresh" on:click={loadDashboard} disabled={loading}>
      {loading ? "Yükleniyor..." : "Yenile"}
    </button>
  </header>

  {#if errors.length}
    <section class="errors">
      {#each errors as err}
        <div>{err}</div>
      {/each}
    </section>
  {/if}

  <section class="grid">
    <article class="card chat">
      <h2>Sohbet Paneli</h2>
      <div class="chat-box">
        {#if replies.length === 0}
          <div class="placeholder">Henüz mesaj yok.</div>
        {:else}
          {#each replies as item}
            <div class={`bubble ${item.role}`}>
              <strong>{item.role === "user" ? "Sen" : "Nasri"}:</strong> {item.text}
            </div>
          {/each}
        {/if}
      </div>
      <div class="chat-input">
        <input bind:value={message} placeholder="Mesaj yaz..." />
        <button on:click={submitChat} disabled={sending}>{sending ? "..." : "Gönder"}</button>
      </div>
    </article>

    <article class="card">
      <h2>Sistem Durumu</h2>
      <div class="kv"><span>Servis</span><strong>{health?.status || "unknown"}</strong></div>
      <div class="kv"><span>Bakım</span><strong>{maintenance?.last_result || "n/a"}</strong></div>
      <div class="kv"><span>Sıradaki Bakım</span><strong>{maintenance?.due ? "Due" : "Planlı"}</strong></div>
    </article>

    <article class="card">
      <h2>Cihaz Listesi</h2>
      <div class="list">
        {#if devices.length === 0}
          <div class="placeholder">Cihaz bulunamadı.</div>
        {:else}
          {#each devices as d}
            <div class="row">
              <span>{d.hostname || d.ip}</span>
              <small>{d.ownership_label}</small>
            </div>
          {/each}
        {/if}
      </div>
    </article>

    <article class="card">
      <h2>Log Görüntüleyici</h2>
      <div class="list mono">
        {#if logs.length === 0}
          <div class="placeholder">Log yok.</div>
        {:else}
          {#each logs as l}
            <div class="row">{l}</div>
          {/each}
        {/if}
      </div>
    </article>
  </section>
</main>

<style>
  :global(html, body) {
    margin: 0;
    min-height: 100%;
    background: radial-gradient(circle at 12% 18%, #f9fafc, #eef2f8 45%, #e9eef7);
    font-family: "Trebuchet MS", "Segoe UI", sans-serif;
    color: #132137;
  }

  .page {
    max-width: 1140px;
    margin: 0 auto;
    padding: 28px 16px 36px;
  }

  .hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }

  .hero h1 {
    margin: 0;
    font-size: clamp(1.6rem, 2.2vw, 2.1rem);
    letter-spacing: 0.02em;
  }

  .hero p {
    margin: 0;
    color: #4a5e7d;
    flex: 1 1 320px;
  }

  .refresh {
    border: 0;
    background: #11386a;
    color: #fff;
    padding: 10px 14px;
    border-radius: 10px;
    cursor: pointer;
  }

  .errors {
    background: #ffe8e8;
    border: 1px solid #f8bebe;
    color: #7c1d1d;
    border-radius: 10px;
    padding: 8px 10px;
    margin-bottom: 14px;
    display: grid;
    gap: 4px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 14px;
  }

  .card {
    grid-column: span 6;
    background: #ffffffcc;
    border: 1px solid #dce4f3;
    border-radius: 14px;
    padding: 14px;
    backdrop-filter: blur(4px);
    min-height: 210px;
  }

  .card h2 {
    margin: 0 0 10px 0;
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #17325c;
  }

  .chat {
    grid-column: span 12;
  }

  .chat-box {
    border: 1px solid #dfe6f7;
    border-radius: 10px;
    padding: 10px;
    min-height: 120px;
    max-height: 220px;
    overflow: auto;
    background: #f7faff;
  }

  .chat-input {
    margin-top: 10px;
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px;
  }

  .chat-input input {
    border: 1px solid #c5d3ee;
    border-radius: 10px;
    padding: 10px 12px;
    font: inherit;
  }

  .chat-input button {
    border: 0;
    border-radius: 10px;
    padding: 10px 14px;
    background: #1f5ca5;
    color: #fff;
    cursor: pointer;
  }

  .bubble {
    padding: 8px 9px;
    border-radius: 8px;
    margin-bottom: 8px;
  }

  .bubble.user {
    background: #e3efff;
  }

  .bubble.assistant {
    background: #f1f6ff;
  }

  .kv {
    display: flex;
    justify-content: space-between;
    border-bottom: 1px solid #e5ebf7;
    padding: 8px 0;
  }

  .list {
    display: grid;
    gap: 8px;
    max-height: 220px;
    overflow: auto;
  }

  .row {
    display: flex;
    justify-content: space-between;
    border: 1px solid #e2e9f6;
    border-radius: 9px;
    padding: 8px;
    background: #fff;
  }

  .mono .row {
    font-family: "Consolas", "Courier New", monospace;
    font-size: 0.85rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .placeholder {
    color: #7a89a5;
    font-style: italic;
  }

  @media (max-width: 900px) {
    .card {
      grid-column: span 12;
    }
  }
</style>
