(() => {
    "use strict";
    const $ = (id) => document.getElementById(id);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const phases = [
        { key: "prepare", label: "Preparar o login", title: "Tudo começa na aplicação.", from: "browser", to: "backend", channel: "front", http: "GET · início do login", copy: "O backend cria uma transação protegida, prepara nonce e PKCE e envia uma prova independente ao navegador por cookie.", fact: "O state viaja na URL. A prova do navegador não: ela fica em um cookie HttpOnly e é exigida no callback.", data: ["state", "nonce", "code_challenge", "code_challenge_method", "browser_proof"], security: ["PKCE exclusivamente S256", "Prova do navegador: HttpOnly e host-only"] },
        { key: "authorize", label: "Abrir o provedor", title: "O navegador muda de destino.", from: "browser", to: "provider", channel: "front", http: "GET · /authorize", copy: "O navegador segue o redirecionamento para o FakeGov. O pedido contém a URI de retorno e os dados de controle, não a senha da aplicação.", fact: "Este é o front-channel: a comunicação passa pelo navegador. O provedor é simulado; não use credenciais reais.", data: ["response_type", "client_id", "redirect_uri", "scope", "state", "nonce"], security: ["Destino e callback previamente configurados"] },
        { key: "provider_login", label: "Autenticar no FakeGov", title: "A identificação acontece no provedor.", from: "browser", to: "provider", channel: "front", http: "POST · /login", copy: "O FakeGov recebe as credenciais fictícias e, se aceitas, emite um código temporário associado ao pedido de autorização.", fact: "Senha incorreta aparece como erro HTTP nesta etapa. Você pode tentar novamente na janela; o observador nunca captura o formulário de credenciais.", data: ["request", "cpf", "password", "code"], security: ["Credenciais do navegador não são capturadas", "Código de autorização vinculado à transação"] },
        { key: "callback", label: "Receber o callback", title: "O navegador volta à aplicação.", from: "browser", to: "backend", channel: "front", http: "GET ou POST · callback", copy: "A aplicação recebe code e state pelo navegador. Receber esses parâmetros ainda não significa que a autenticação foi aceita.", fact: "Callbacks incompletos ou com uma prova de navegador inválida devem ser rejeitados antes de consultar o endpoint de token.", data: ["code", "state", "browser_proof"], security: ["Parâmetros de callback obrigatórios", "Ainda não representa uma sessão autenticada"] },
        { key: "binding", label: "Vincular ao navegador", title: "A transação precisa pertencer a este navegador.", from: "backend", to: "backend", channel: "internal", http: "Validação local · inferida", copy: "Antes da troca do código, o adapter verifica a prova do navegador e o núcleo decodifica e valida o state protegido.", fact: "Esta aceitação é inferida porque o fluxo chegou ao pedido de token. O observador não mede nem reexecuta cada validação interna.", data: ["browser_proof", "state", "code_verifier"], security: ["Prova independente do state", "Autenticidade e validade temporal da transação"] },
        { key: "token", label: "Trocar código", title: "Agora, os servidores conversam.", from: "backend", to: "provider", channel: "back", http: "POST · /token", copy: "O backend envia o código, a URI de retorno e o verificador PKCE. As credenciais do cliente autenticam a requisição. Tokens ficam no backend.", fact: "No FakeGov integrado, o HTTPX usa transporte em memória. São mensagens HTTP reais do cliente, mas não uma conexão de rede com o gov.br.", data: ["grant_type", "code", "redirect_uri", "code_verifier", "access_token", "id_token"], security: ["Autenticação do cliente", "Código de autorização de uso único", "Verificador compatível com o desafio S256"] },
        { key: "jwks", label: "Consultar chaves", title: "Buscar chaves não é validar o token.", from: "backend", to: "provider", channel: "back", http: "GET · /jwk", copy: "O backend consulta o conjunto de chaves públicas do provedor para verificar a assinatura do ID token recebido.", fact: "A resposta contém somente chaves públicas. Um HTTP 200 nesta etapa não prova, sozinho, que assinatura ou claims foram aceitas.", data: ["keys"], security: ["Consulta às chaves públicas do provedor"] },
        { key: "validation", label: "Validar o ID token", title: "Assinatura e contexto precisam conferir.", from: "backend", to: "backend", channel: "internal", http: "Validação local · inferida", copy: "O núcleo valida o token com as chaves recebidas e verifica seu contexto: issuer, audience, nonce e declarações temporais.", fact: "A aceitação é inferida pelo início da consulta UserInfo. Não há tempos individuais ou um checklist independente de cada claim no trace.", data: ["iss", "aud", "nonce", "exp", "iat"], security: ["Assinatura, algoritmo e chave permitidos", "Issuer, audience e nonce esperados", "Declarações temporais válidas"] },
        { key: "userinfo", label: "Consultar identidade", title: "O perfil deve corresponder ao token.", from: "backend", to: "provider", channel: "back", http: "GET · /userinfo", copy: "O backend usa o access token para consultar UserInfo. O núcleo compara o sub retornado com o sujeito do ID token.", fact: "O painel mostra o formato da resposta, mas oculta CPF, nome, e-mail e demais dados de identidade, inclusive no JSON exportado.", data: ["sub", "name", "email", "email_verified"], security: ["Bearer token permanece no backend", "Sujeito de UserInfo deve coincidir com o ID token"] },
        { key: "result", label: "Concluir o callback", title: "O callback respondeu. Sessão é outra etapa.", from: "backend", to: "browser", channel: "front", http: "Resposta do callback", copy: "O adapter entrega o resultado ao callback da aplicação e remove a prova dessa transação. O status exibido é a resposta real recebida.", fact: "A biblioteca não cria automaticamente a sessão do seu sistema. A demo apresenta o resultado; a aplicação consumidora define sua própria sessão.", data: ["browser_proof"], security: ["Prova da transação removida", "Outras abas e cookies de sessão preservados"] }
    ];
    const logout = { key: "logout", label: "Logout", title: "Encerrar no provedor.", from: "browser", to: "provider", channel: "front", http: "GET · /logout", copy: "O fluxo usa o destino de retorno previamente registrado.", fact: "A sessão local da aplicação deve ser encerrada pela própria aplicação.", data: ["post_logout_redirect_uri"], security: ["Redirecionamento de retorno validado"] };
    const labels = { browser: "Navegador", backend: "Backend", provider: "FakeGov" };
    let snapshot = null, index = -1, phase = phases[0], tab = "summary", playing = false;
    let active = false, starting = false, popup = null, playbackTimer = null, pollTimer = null, generation = 0;
    const events = () => snapshot ? snapshot.events : [];
    const event = () => events()[index] || null;
    function node(tag, text, className) {
        const n = document.createElement(tag);
        if (text !== undefined)
            n.textContent = text;
        if (className)
            n.className = className;
        return n;
    }
    function status(title, note, error = false) {
        $("capture-state").textContent = title;
        $("capture-note").textContent = note;
        $("status-dot").className = "dot" + (error ? " error" : active ? " live" : "");
    }
    function notice(text, error = false) { $("notice").textContent = text; $("notice").className = "notice" + (error ? " error" : ""); }
    function controls() {
        $("play").disabled = !events().length;
        $("play").textContent = playing ? "Pausar" : "Reproduzir";
        $("previous").disabled = index <= 0;
        $("next").disabled = index >= events().length - 1;
        $("replay").disabled = !events().length;
        $("export").disabled = !events().length;
        $("clear").disabled = starting || (!snapshot && !active);
        $("debug-toggle").disabled = starting;
        $("start").disabled = active || starting;
        $("progress").style.width = events().length ? ((index + 1) / events().length * 100) + "%" : "0%";
        $("event-position").textContent = events().length ? `${Math.max(0, index + 1)} de ${events().length} eventos exibidos` : "Nenhum evento capturado";
    }
    function timeline() {
        const focused = document.activeElement?.dataset.phase;
        $("steps").replaceChildren();
        let done = 0;
        phases.forEach((step, order) => {
            const matches = events().map((item, i) => ({ item, i })).filter(({ item }) => item.phase === step.key);
            const seen = matches.filter(({ i }) => i <= index).at(-1);
            if (seen)
                done++;
            const row = node("li");
            const b = node("button", undefined, "step" + (phase.key === step.key ? " selected" : "") + (seen ? seen.item.status === "error" ? " failed" : " done" : ""));
            b.type = "button";
            b.dataset.phase = step.key;
            if (phase.key === step.key)
                b.setAttribute("aria-current", "step");
            b.append(node("span", seen ? seen.item.status === "error" ? "!" : "✓" : String(order + 1).padStart(2, "0"), "step-number"));
            const title = node("span");
            title.append(node("span", step.label, "step-title"));
            title.append(node("span", seen ? seen.item.status === "error" ? "Falha observada" : seen.item.evidence === "inferred" ? "Aceitação inferida" : "Observado" : matches.length ? "Capturado · na fila" : "Aguardando", "step-status"));
            b.append(title);
            b.addEventListener("click", () => { pause(); if (matches.length)
                select(matches.at(-1).i);
            else {
                index = -1;
                phase = step;
                render();
            } });
            row.append(b);
            $("steps").append(row);
        });
        if (focused)
            $("steps").querySelector(`[data-phase="${focused}"]`)?.focus({ preventScroll: true });
        $("step-count").textContent = `${String(done).padStart(2, "0")} / 10`;
    }
    function diagram() {
        const x = { browser: 100, backend: 300, provider: 500 };
        document.querySelectorAll(".actor").forEach(n => n.classList.remove("active"));
        $("actor-" + phase.from).classList.add("active");
        $("actor-" + phase.to).classList.add("active");
        const path = phase.from === phase.to ? `M300 24 C390 24 390 80 300 80` : `M${x[phase.from]} 65 H${x[phase.to]}`;
        const kind = phase.channel + (event()?.status === "error" ? " error" : "");
        $("wire").setAttribute("d", path);
        $("wire").setAttribute("class", "wire visible " + kind);
        const hasResponse = !!(event()?.request && event()?.response && phase.from !== phase.to);
        const responsePath = `M${x[phase.to]} 96 H${x[phase.from]}`;
        $("wire-response").setAttribute("d", responsePath);
        $("wire-response").setAttribute("class", "wire response " + (hasResponse ? "visible " : "") + kind);
        $("reply-packet").setAttribute("class", "packet reply " + kind);
        $("reply-packet").style.offsetPath = `path('${responsePath}')`;
        $("packet").setAttribute("class", "packet " + (hasResponse ? "round-trip " : "") + kind);
        $("packet").style.offsetPath = `path('${path}')`;
        if (!reduced.matches && event()) {
            void $("packet").getBoundingClientRect();
            $("packet").classList.add("animate");
            if (hasResponse) $("reply-packet").classList.add("animate");
        }
        $("wire-label").textContent = phase.http + (hasResponse ? ` · resposta ${event().response.status}` : "");
        $("graph-desc").textContent = `${labels[phase.from]} para ${labels[phase.to]}: ${phase.label}`;
        $("channel").textContent = { front: "Pelo navegador", back: "Backchannel · local", internal: "Validação local" }[phase.channel];
    }
    function detailRow(dl, key, value) { dl.append(node("dt", key), node("dd", value)); }
    function jsonBlock(root, title, value) { root.append(node("h3", title), node("pre", JSON.stringify(value, null, 2))); }
    function panel() {
        const root = $("technical-content"), item = event();
        root.replaceChildren();
        root.setAttribute("aria-labelledby", "tab-" + tab);
        if (tab === "summary") {
            root.append(node("h3", item ? "Evidência da etapa" : "Antes de começar"));
            if (!item)
                root.append(node("div", "⌘", "empty-glyph"), node("p", "Conceito, não uma execução.", "empty-title"), node("p", "Selecione Iniciar fluxo para observar a autenticação. Este texto explica o fluxo, mas não afirma que uma verificação já aconteceu."));
            const dl = node("dl");
            detailRow(dl, "Etapa", phase.label);
            detailRow(dl, "Origem → destino", `${labels[phase.from]} → ${labels[phase.to]}`);
            detailRow(dl, "Evidência", !item ? "Conceitual" : item.evidence === "inferred" ? "Inferida da progressão do core" : "Observada na fronteira HTTP");
            if (item) {
                detailRow(dl, "Resultado", item.status === "error" ? "Falha" : item.status === "running" ? "Aguardando resposta" : "Etapa registrada");
                detailRow(dl, "Duração medida", item.duration_ms === null ? "Não medida individualmente" : `${item.duration_ms} ms`);
            }
            root.append(dl, node("p", "No FakeGov integrado, as mensagens HTTP de backchannel passam pelo transporte local em memória. Não são chamadas ao serviço oficial."));
        }
        else if (tab === "http") {
            if (!item || item.evidence === "inferred")
                root.append(node("p", "Não existe uma requisição HTTP isolada para esta explicação. Nenhum request ou response foi fabricado."));
            else {
                if (item.request)
                    jsonBlock(root, "Request · saneado", item.request);
                if (item.response)
                    jsonBlock(root, "Response · saneado", item.response);
                else
                    root.append(node("p", item.status === "error" ? "A execução falhou antes de uma resposta HTTP observável. Nenhum status foi inventado." : "Resposta ainda não observada ou representada em outra etapa."));
            }
        }
        else if (tab === "data") {
            root.append(node("h3", "Artefatos relevantes"), node("p", "Lista didática dos artefatos envolvidos. A aba HTTP indica os campos efetivamente observados. Nenhum valor de autenticação é revelado, nem parcialmente."));
            const dl = node("dl");
            phase.data.forEach(key => detailRow(dl, key, "[oculto]"));
            root.append(dl, node("p", "Claims e tokens não são decodificados pelo observador. Dados pessoais do perfil também são omitidos."));
        }
        else if (tab === "security") {
            root.append(node("h3", "O que protege esta etapa"));
            phase.security.forEach(text => { const card = node("div", undefined, "security-item"); card.append(node("strong", text), node("p", item?.evidence === "inferred" ? "Aceitação inferida; sem medição independente deste item." : "Contrato explicado. Não é uma auditoria independente.")); root.append(card); });
            root.append(node("p", phase.fact));
            if (item?.status === "error")
                root.append(node("p", "A etapa retornou erro. As etapas seguintes não devem ser consideradas validadas.", "inference-note"));
        }
        else {
            root.append(node("h3", "Eventos capturados"));
            if (!events().length)
                root.append(node("p", "Ainda não há eventos nesta captura."));
            else
                jsonBlock(root, "Ordem real, não tempo de animação", events().map(e => ({ id: e.id, phase: e.phase, status: e.status, evidence: e.evidence, at_ms: e.at_ms, duration_ms: e.duration_ms, http_status: e.response?.status ?? null })));
        }
    }
    function render() {
        const item = event();
        $("stage-kicker").textContent = item ? `EVENTO ${String(index + 1).padStart(2, "0")} · ${item.status === "error" ? "FALHA" : "FLUXO LOCAL"}` : "EXPLICAÇÃO DIDÁTICA";
        $("stage-title").textContent = item?.status === "error" ? `Falha na etapa: ${phase.label}.` : phase.title;
        $("stage-copy").textContent = phase.copy;
        $("stage-fact").querySelector("p").textContent = phase.fact;
        $("evidence").textContent = !item ? "Conceitual · sem captura" : item.evidence === "inferred" ? "Validação inferida" : "HTTP observado";
        $("event-timing").textContent = item?.duration_ms !== null && item ? `Tempo real: ${item.duration_ms} ms` : "Tempo individual: não medido";
        timeline();
        diagram();
        panel();
        controls();
    }
    function select(i) { if (i < 0 || i >= events().length)
        return; index = i; phase = phases.find(p => p.key === event().phase) || logout; render(); }
    function schedulePlayback() { clearTimeout(playbackTimer); if (!playing)
        return; playbackTimer = setTimeout(() => { if (index < events().length - 1)
        select(index + 1);
    else if (!active) {
        pause();
        return;
    } schedulePlayback(); }, Number($("speed").value)); }
    function pause() { playing = false; clearTimeout(playbackTimer); controls(); }
    function play() { playing = true; controls(); schedulePlayback(); }
    async function api(method) {
        const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 6000);
        try {
            const response = await fetch(DEMO_CONFIG.trace, { method, headers: { "X-Govbr-Demo": "1" }, credentials: "same-origin", cache: "no-store", signal: abort.signal });
            if (!response.ok)
                throw new Error(String(response.status));
            return response.status === 204 ? null : await response.json();
        }
        finally {
            clearTimeout(timeout);
        }
    }
    function closePopup() { if (popup && !popup.closed)
        popup.close(); popup = null; }
    async function poll(run, failures = 0) {
        if (run !== generation || !active)
            return;
        try {
            const data = await api("GET");
            if (run !== generation)
                return;
            snapshot = data;
            if (snapshot.completed) {
                active = false;
                closePopup();
                const failed = events().some(e => e.phase === "result" && e.status === "error");
                status(failed ? "Callback concluído com erro" : "Captura concluída", `${events().length} eventos · reprodução independente`, failed);
                notice(failed ? "O callback retornou erro. Explore as etapas para localizar a última comunicação observada." : "A comunicação real terminou. Acompanhe a reprodução ou avance manualmente; nenhum pedido será reenviado.", failed);
            }
            else if (popup?.closed) {
                active = false;
                status("Captura interrompida", "A janela foi fechada; eventos parciais preservados.");
                notice("A janela de autenticação foi fechada. Você pode examinar ou exportar a captura parcial.");
            }
            else
                status("Capturando comunicação", `${events().length} eventos · conclua o login na janela do FakeGov`);
            if (snapshot.truncated)
                notice("Limite de 128 eventos atingido. Esta captura é parcial; limpe-a antes de uma nova tentativa.", true);
            timeline();
            panel();
            controls();
            if (active)
                pollTimer = setTimeout(() => poll(run), 700);
        }
        catch (error) {
            if (run !== generation)
                return;
            if (failures < 2) {
                notice("A leitura do trace falhou. Tentando reconectar ao processo local…", true);
                pollTimer = setTimeout(() => poll(run, failures + 1), 1200);
            }
            else {
                active = false;
                pause();
                closePopup();
                status("Captura indisponível", "Trace expirado, servidor reiniciado ou conexão indisponível.", true);
                notice("Não foi possível ler o trace. Preserve a captura parcial ou limpe e inicie novamente. Use um único worker na demo.", true);
                controls();
            }
        }
    }
    $("start").addEventListener("click", async () => {
        const run = ++generation;
        clearTimeout(pollTimer);
        pause();
        closePopup();
        popup = window.open("about:blank", "govbr-debug-authentication", "popup,width=520,height=740,resizable=yes,scrollbars=yes");
        if (!popup) {
            status("Janela bloqueada", "Permita popups para esta demo.", true);
            notice("O navegador bloqueou a janela. Permita popups e selecione Iniciar fluxo novamente.", true);
            return;
        }
        active = true;
        starting = true;
        snapshot = null;
        index = -1;
        phase = phases[0];
        render();
        status("Preparando captura", "Criando um trace privado para este navegador.");
        try {
            const created = await api("POST");
            if (run !== generation)
                return;
            snapshot = created;
            starting = false;
            popup.location.replace(DEMO_CONFIG.login);
            popup.focus();
            notice("Use somente as credenciais fictícias configuradas no FakeGov. A senha não será capturada pelo painel.");
            if (!reduced.matches)
                play();
            else
                notice("Movimento reduzido ativo. Conclua o login e use Próxima etapa ou Reproduzir para explorar.");
            controls();
            poll(run);
        }
        catch (error) {
            if (run !== generation)
                return;
            starting = false;
            active = false;
            closePopup();
            status("Não foi possível iniciar", "Confira a origem do callback e a conexão local.", true);
            notice("A captura não foi iniciada. A demo e o callback precisam usar a mesma origem configurada; nenhum fluxo de autenticação foi enviado.", true);
            controls();
        }
    });
    async function clear() { if (starting) return false; starting = true; ++generation; active = false; clearTimeout(pollTimer); pause(); closePopup(); try {
        await api("DELETE");
        starting = false;
        snapshot = null;
        index = -1;
        phase = phases[0];
        status("Captura apagada", "Nenhum trace retido para este navegador.");
        notice("Inicie um novo login para capturar outra execução. Cookies de autenticação e sessão da aplicação não são removidos por este controle.");
        render();
        return true;
    }
    catch (error) {
        starting = false;
        status("Não foi possível apagar", "A captura expira automaticamente em até 10 minutos.", true);
        notice("O servidor não confirmou a exclusão. A captura foi interrompida nesta página; o trace remoto mantém sua expiração automática.", true);
        controls();
        return false;
    } }
    $("clear").addEventListener("click", clear);
    async function exitDebug(event) { event.preventDefault(); if (starting)
        return; const cleared = await clear(); if (cleared)
        window.location.assign(DEMO_CONFIG.home); }
    $("debug-toggle").addEventListener("click", exitDebug);
    $("normal-link").addEventListener("click", exitDebug);
    $("play").addEventListener("click", () => playing ? pause() : play());
    $("previous").addEventListener("click", () => { pause(); select(index - 1); });
    $("next").addEventListener("click", () => { pause(); select(index + 1); });
    $("replay").addEventListener("click", () => { pause(); index = -1; phase = phases[0]; render(); play(); });
    $("speed").addEventListener("change", schedulePlayback);
    $("export").addEventListener("click", () => { if (!snapshot)
        return; const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const link = node("a"); link.href = url; link.download = "govbr-auth-trace-saneado.json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
    const tabs = Array.from(document.querySelectorAll("[data-tab]"));
    function activateTab(button) { tab = button.dataset.tab; tabs.forEach(b => { const selected = b === button; b.setAttribute("aria-selected", String(selected)); b.tabIndex = selected ? 0 : -1; }); panel(); }
    tabs.forEach((b, i) => { b.addEventListener("click", () => activateTab(b)); b.addEventListener("keydown", e => { const move = { ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1 }[e.key]; if (move !== undefined) {
        e.preventDefault();
        activateTab(tabs[move]);
        tabs[move].focus();
    } }); });
    reduced.addEventListener("change", () => { if (reduced.matches)
        pause(); $("motion-note").textContent = reduced.matches ? "Movimento reduzido: animações desativadas. Reprodução manual disponível." : "Pausar afeta somente a apresentação, nunca o tempo de validade do login."; });
    if (reduced.matches)
        $("motion-note").textContent = "Movimento reduzido: animações desativadas. Reprodução manual disponível.";
    window.addEventListener("message", e => { if (e.origin !== window.location.origin || e.source !== popup)
        return; if (e.data?.type === "govbr-authentication-completed")
        popup?.focus(); });
    window.addEventListener("pagehide", () => { ++generation; active = false; clearTimeout(pollTimer); clearTimeout(playbackTimer); closePopup(); });
    render();
})();
