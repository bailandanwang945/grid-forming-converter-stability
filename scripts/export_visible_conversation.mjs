import { createReadStream, statSync, mkdirSync, writeFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

// Explicitly authorized visible-text export, not a raw assistant-state backup.
export function sanitizeText(value) {
  let text = value;
  const redactions = {};
  const replace = (name, pattern, replacement) => {
    text = text.replace(pattern, (...args) => {
      redactions[name] = (redactions[name] ?? 0) + 1;
      return typeof replacement === 'function' ? replacement(...args) : replacement;
    });
  };
  replace('user_directory', /([A-Za-z]:[\\/]+Users[\\/]+)[^\\/\s<>:"']+/gi, (_match, prefix) => `${prefix}[USER]`);
  replace('wechat_identifier', /wxid_[A-Za-z0-9_]+/gi, '[WECHAT_ID]');
  replace('api_token', /\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b/g, '[REDACTED_TOKEN]');
  replace('bearer_token', /\bBearer\s+[A-Za-z0-9_.~+\/-]{20,}=*/gi, 'Bearer [REDACTED_TOKEN]');
  replace('assigned_secret', /((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret)["']?\s*[:=]\s*["']?)([A-Za-z0-9_./+\-=]{8,})/gi, (_match, prefix) => `${prefix}[REDACTED_SECRET]`);
  replace('private_key', /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/g, '[REDACTED_PRIVATE_KEY]');
  replace('url_credentials', /(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, (_match, protocol) => `${protocol}[REDACTED_AUTH]@`);
  replace('jwt', /\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{15,}\b/g, '[REDACTED_JWT]');
  replace('phone_number', /(?<![\d.])(?:\+86[ -]?)?1[3-9]\d{9}(?![\d.])/g, '[REDACTED_PHONE]');
  return { text, redactions };
}

export function extractVisibleMessage(record) {
  if (record.type !== 'response_item' || record.payload?.type !== 'message') return null;
  const message = record.payload;
  if (!['user', 'assistant'].includes(message.role)) return null;
  const channel = message.channel ?? message.phase;
  if (message.role === 'assistant' && ![undefined, 'final', 'final_answer', 'commentary'].includes(channel)) return null;
  const contents = Array.isArray(message.content) ? message.content : [{ type: 'input_text', text: message.content }];
  const paragraphs = [];
  let attachments = 0;
  for (const part of contents) {
    if (['input_text', 'output_text', 'text'].includes(part.type) && typeof part.text === 'string') paragraphs.push(part.text);
    else if (['input_image', 'image', 'input_audio', 'audio', 'input_file', 'file'].includes(part.type)) attachments++;
  }
  let text = paragraphs.join('\n\n');
  // Environment/context scaffolding is not a human chat message.
  if (/^\s*(?:# AGENTS\.md instructions|<INSTRUCTIONS>\s*#.*AGENTS\.md)/i.test(text)) return null;
  text = text.replace(/<(environment_context|in-app-browser-context|external_codex_apps_open_page|oai-mem-citation)\b[^>]*>[\s\S]*?<\/\1>/gi, '');
  const reply = text.match(/<send_user_message_question_reply>\s*([\s\S]*?)\s*<\/send_user_message_question_reply>/);
  if (reply) {
    try {
      const answers = JSON.parse(reply[1]);
      text = text.replace(reply[0], answers.map(item => `问题：${item.question}\n\n回答：${item.answer}`).join('\n\n'));
    } catch { /* Preserve visible text if the answer wrapper is not valid JSON. */ }
  }
  text = text.trim();
  if (attachments) text += `${text ? '\n\n' : ''}[附件提示：本条消息另含 ${attachments} 个非文本附件；本档案不复制附件二进制内容。]`;
  if (!text) return null;
  const sanitized = sanitizeText(text);
  return { role: message.role, channel: channel ?? null, timestamp: record.timestamp ?? null, attachments, ...sanitized };
}

export async function exportConversation({ source, threadId, output }) {
  if (!/\.md$/i.test(output) || resolve(source) === resolve(output)) throw new Error('Output must be a separate Markdown file; source is read-only.');
  const snapshotBytes = statSync(source).size;
  const input = createReadStream(source, { end: snapshotBytes - 1 });
  const lines = createInterface({ input, crlfDelay: Infinity });
  const stats = {
    threadId, exportedAt: new Date().toISOString(), snapshotBytes,
    records: 0, recordTypes: {}, visibleMessages: 0, roles: {}, channels: {},
    omittedMessageRecords: 0, compactionRecords: 0, partialSnapshotRecords: 0,
    attachmentNotices: 0, redactions: {}, firstMessageAt: null, lastMessageAt: null,
  };
  const rendered = [];
  let verifiedIdentity = false;
  for await (const line of lines) {
    if (!line.trim()) continue;
    let record;
    try { record = JSON.parse(line); }
    catch {
      // Only an unfinished last record is permitted, as the active log may append.
      stats.partialSnapshotRecords++;
      if (stats.partialSnapshotRecords > 1) throw new Error('More than one invalid source record; export refused.');
      continue;
    }
    if (stats.partialSnapshotRecords) throw new Error('Invalid record was not the final snapshot record; export refused.');
    stats.records++;
    stats.recordTypes[record.type] = (stats.recordTypes[record.type] ?? 0) + 1;
    if (record.type === 'session_meta') {
      if (record.payload?.id !== threadId) throw new Error('Source thread identity does not match; export refused.');
      verifiedIdentity = true;
    }
    if (record.type === 'compacted') stats.compactionRecords++;
    const message = extractVisibleMessage(record);
    if (!message) {
      if (record.type === 'response_item' && record.payload?.type === 'message') stats.omittedMessageRecords++;
      continue;
    }
    stats.visibleMessages++;
    stats.roles[message.role] = (stats.roles[message.role] ?? 0) + 1;
    const channel = message.channel ?? 'unspecified';
    stats.channels[channel] = (stats.channels[channel] ?? 0) + 1;
    stats.attachmentNotices += message.attachments;
    stats.firstMessageAt ??= message.timestamp;
    stats.lastMessageAt = message.timestamp;
    for (const [key, count] of Object.entries(message.redactions)) stats.redactions[key] = (stats.redactions[key] ?? 0) + count;
    const speaker = message.role === 'user' ? '用户' : '助手';
    rendered.push(`## ${String(stats.visibleMessages).padStart(4, '0')} · ${speaker} · ${message.timestamp ?? '时间未记录'}\n\n${message.text}\n\n---\n`);
  }
  if (!verifiedIdentity || !stats.visibleMessages) throw new Error('No verified visible conversation was found.');
  const header = `# 项目会话正文（隐私脱敏版）\n\n导出时间：${stats.exportedAt}\n\n本档案按时间顺序保存本会话本地记录中可恢复的用户正文和助手可见回复，共 ${stats.visibleMessages} 条（用户 ${stats.roles.user ?? 0} 条、助手 ${stats.roles.assistant ?? 0} 条）。正文未作总结改写，仅去除运行环境附加块，并对个人目录、微信标识、疑似凭据和手机号进行脱敏。\n\n不包含系统／开发者指令、隐藏推理、工具原始输入输出、账号文件或附件二进制内容。图片与文件名若出现在正文中则予以保留。压缩上下文的内部摘要不作为原始发言；本地记录之外、记录本身已省略或已截断的内容无法恢复。本档案不是整个账号的聊天备份，也不包含其他会话。\n\n覆盖的可见消息时间：${stats.firstMessageAt} 至 ${stats.lastMessageAt}（UTC）。导出只读取固定大小快照；之后新增的消息不在本版内。\n\n完整性与脱敏统计见同名 JSON 清单。原始会话日志不上传。历史回复中的推断、实验数字和“已完成”表述按当时原话保存，不代表本次再次验证；当前状态以项目文档及测试记录为准。\n\n---\n\n`;
  const body = header + rendered.join('\n');
  stats.outputBytes = Buffer.byteLength(body);
  stats.outputSha256 = createHash('sha256').update(body).digest('hex');
  stats.identityVerified = verifiedIdentity;
  stats.scope = 'Single-thread visible user and assistant text; not raw logs or hidden reasoning';
  stats.limitations = ['Non-text attachments are not copied', 'Compaction summaries are excluded', 'Source omissions or truncations cannot be reconstructed', 'Messages after the fixed snapshot are not included'];
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, body, 'utf8');
  writeFileSync(output.replace(/\.md$/i, '') + '.manifest.json', JSON.stringify(stats, null, 2) + '\n', 'utf8');
  return stats;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, all) => index % 2 ? pairs : [...pairs, [value, all[index + 1]]], []));
  if (!args['--source'] || !args['--thread'] || !args['--out']) throw new Error('Usage: node export_visible_conversation.mjs --source <single session> --thread <expected id> --out <markdown>');
  const stats = await exportConversation({ source: args['--source'], threadId: args['--thread'], output: args['--out'] });
  console.log(JSON.stringify(stats, null, 2));
}
