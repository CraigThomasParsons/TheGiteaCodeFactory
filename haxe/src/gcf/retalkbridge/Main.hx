package gcf.retalkbridge;

import gcf.retalkbridge.Policy.Message;
import gcf.retalkbridge.Policy.Outcome;
import haxe.Json;
import python.Syntax;
import sys.FileSystem;
import sys.io.File;

/** A failure reported to the user as one line on stderr with exit code 1. **/
class Failure extends haxe.Exception {}

/** Output of one child process. **/
typedef Run = {
	var code:Int;
	var out:String;
	var err:String;
}

/**
	retalk-bridge: automatic two-way messaging between two agent CLIs over retalk.

	Commands (see skills/retalk-bridge/SKILL.md):
	  hook --side S           run as a Claude Code or Codex lifecycle hook (JSON on stdin)
	  tick [--side S]         watcher pass: fetch new mail and wake an idle side
	  fetch --side S          fetch new mail into the side's local spool only
	  send --side S TEXT      send TEXT to the side's peer (saved to retalk history)
	  status                  print the bridge state as JSON (no message text)
	  install-hooks / uninstall-hooks --claude-settings P --codex-hooks P --command C
	Exit codes: 0 ok, 1 runtime failure, 2 usage error.
**/
class Main {
	static var config:Dynamic;
	static var configPath:String;

	static function main():Void {
		var args = Sys.args();
		if (args.length == 0 || args[0] == "-h" || args[0] == "--help") {
			Sys.println(USAGE);
			Sys.exit(args.length == 0 ? 2 : 0);
		}
		var command = args.shift();
		var options = parseOptions(args);
		try {
			switch (command) {
				case "install-hooks":
					installHooks(options, true);
				case "uninstall-hooks":
					installHooks(options, false);
				default:
					loadConfig();
					switch (command) {
						case "hook":
							hook(requireSide(options));
						case "tick":
							var only = options.get("side");
							if (only != null)
								sideConfig(only);
							for (side in sideNames())
								if (only == null || only == side)
									tick(side);
						case "fetch":
							var side = requireSide(options);
							Sys.println(Json.stringify({side: side, fetched: fetch(side)}));
						case "send":
							var side = requireSide(options);
							var text = options.get("_");
							if (text == null || text == "")
								usage("send needs the message text");
							var hop = options.exists("hop") ? Std.parseInt(options.get("hop")) : 0;
							if (!send(side, text, hop == null ? 0 : hop))
								Sys.exit(1);
						case "status":
							status();
						default:
							usage("unknown command " + command);
					}
			}
		} catch (e:Failure) {
			Sys.stderr().writeString("retalk-bridge: " + e.message + "\n");
			Sys.exit(1);
		}
	}

	static var USAGE = "usage: retalk_bridge.py {hook|tick|fetch|send|status|install-hooks|uninstall-hooks} [--side SIDE] ...\n"
		+ "  hook --side S        lifecycle hook for Claude Code / Codex (event JSON on stdin)\n"
		+ "  tick [--side S]      watcher pass: fetch mail, wake an idle side, send its reply\n"
		+ "  fetch --side S       fetch new mail into the local spool\n"
		+ "  send --side S [--hop N] [--] TEXT\n"
		+ "                       send TEXT to the side's peer (put -- before a TEXT starting with -)\n"
		+ "  status               bridge state as JSON (no message text)\n"
		+ "  install-hooks|uninstall-hooks --claude-settings FILE --codex-hooks FILE --command CMD\n"
		+ "config: $RETALK_BRIDGE_CONFIG or ~/.config/retalk-bridge/config.json";

	static function usage(message:String):Void {
		Sys.stderr().writeString("retalk-bridge: " + message + "\n");
		Sys.exit(2);
	}

	static function parseOptions(args:Array<String>):Map<String, String> {
		var options = new Map<String, String>();
		var i = 0;
		var positionalOnly = false;
		while (i < args.length) {
			var arg = args[i];
			if (!positionalOnly && arg == "--") {
				positionalOnly = true;
				i++;
			} else if (!positionalOnly && StringTools.startsWith(arg, "--")) {
				if (i + 1 >= args.length)
					usage(arg + " needs a value");
				options.set(arg.substr(2), args[i + 1]);
				i += 2;
			} else {
				if (options.exists("_"))
					usage("unexpected argument " + arg + " (quote the message text as one argument)");
				options.set("_", arg);
				i++;
			}
		}
		return options;
	}

	// ---------------------------------------------------------------- config and state

	static function home():String {
		var value = Sys.getEnv("HOME");
		return value == null ? "/" : value;
	}

	static function expand(path:String):String {
		if (path == "~")
			return home();
		return StringTools.startsWith(path, "~/") ? home() + path.substr(1) : path;
	}

	static function loadConfig():Void {
		var fromEnv = Sys.getEnv("RETALK_BRIDGE_CONFIG");
		configPath = fromEnv != null && fromEnv != "" ? fromEnv : home() + "/.config/retalk-bridge/config.json";
		if (!FileSystem.exists(configPath))
			throw new Failure("no config at " + configPath + " (see skills/retalk-bridge/SKILL.md)");
		config = Policy.parseJson(File.getContent(configPath));
		if (config.sides == null)
			throw new Failure(configPath + " has no \"sides\"");
	}

	static function setting(name:String, fallback:Dynamic):Dynamic {
		var value = Reflect.field(config, name);
		return value == null ? fallback : value;
	}

	static function sideNames():Array<String> {
		var names = Reflect.fields(config.sides);
		names.sort(Reflect.compare);
		return names;
	}

	static function sideConfig(side:String):Dynamic {
		var value = Reflect.field(config.sides, side);
		if (value == null)
			usage("unknown side " + side + "; configured: " + sideNames().join(", "));
		return value;
	}

	static function requireSide(options:Map<String, String>):String {
		var side = options.get("side");
		if (side == null)
			usage("--side is required");
		sideConfig(side);
		return side;
	}

	static function stateDir(side:String):String {
		var dir = expand(setting("state_dir", "~/.local/state/retalk-bridge")) + "/" + side;
		if (!FileSystem.exists(dir))
			FileSystem.createDirectory(dir);
		Syntax.code("__import__('os').chmod({0}, 0o700)", dir);
		return dir;
	}

	static function readJson(path:String, fallback:Dynamic):Dynamic {
		if (!FileSystem.exists(path))
			return fallback;
		return try Policy.parseJson(File.getContent(path)) catch (e:Dynamic) fallback;
	}

	/** Write JSON atomically with owner-only permissions (state can hold message text). **/
	static function writeJson(path:String, value:Dynamic):Void {
		// A name of its own per writer: concurrent hooks may write the same file.
		var tmp = path + "." + Syntax.code("__import__('os').getpid()") + "." + Std.random(1000000000) + ".tmp";
		File.saveContent(tmp, Json.stringify(value, null, " ") + "\n");
		Syntax.code("__import__('os').chmod({0}, 0o600)", tmp);
		FileSystem.rename(tmp, path);
	}

	static function now():Float {
		return Sys.time();
	}

	static function stamp():String {
		return Syntax.code("__import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds')");
	}

	/** Append one event to the side's log (JSON lines, owner-only). **/
	static function log(side:String, event:String, fields:Dynamic):Void {
		var record:Dynamic = {at: stamp(), side: side, event: event};
		if (fields != null)
			for (field in Reflect.fields(fields))
				Reflect.setField(record, field, Reflect.field(fields, field));
		var path = stateDir(side) + "/bridge.log";
		var out = File.append(path, false);
		out.writeString(Json.stringify(record) + "\n");
		out.close();
		Syntax.code("__import__('os').chmod({0}, 0o600)", path);
	}

	/** Run `body` holding an exclusive flock on `path`; with `wait` false, return false when it is held. **/
	static function withLock(path:String, wait:Bool, body:Void->Void):Bool {
		var handle:Dynamic = Syntax.code("open({0}, 'a')", path);
		var fcntl:Dynamic = Syntax.code("__import__('fcntl')");
		var flags:Int = wait ? fcntl.LOCK_EX : (fcntl.LOCK_EX | fcntl.LOCK_NB);
		var locked = try {
			fcntl.flock(handle, flags);
			true;
		} catch (e:Dynamic) false;
		if (!locked) {
			handle.close();
			return false;
		}
		try {
			body();
		} catch (e:Dynamic) {
			handle.close();
			throw e;
		}
		handle.close();
		return true;
	}

	static function run(command:Array<String>, cwd:Null<String>, timeout:Float, child:Bool):Run {
		var env:Dynamic = Syntax.code("dict(__import__('os').environ)");
		if (child)
			Syntax.code("{0}['RETALK_BRIDGE_CHILD'] = '1'", env);
		try {
			var done:Dynamic = Syntax.code("__import__('subprocess').run({0}, cwd={1}, env={2}, capture_output=True, text=True, timeout={3}, stdin=__import__('subprocess').DEVNULL)",
				command, cwd, env, timeout);
			return {code: done.returncode, out: done.stdout, err: done.stderr};
		} catch (e:Dynamic) {
			return {code: 124, out: "", err: Std.string(e)};
		}
	}

	// ---------------------------------------------------------------- spool

	/** The side's spool: every message received, with its delivery state. **/
	static function spool(side:String):Array<Dynamic> {
		return readJson(stateDir(side) + "/spool.json", []);
	}

	static function saveSpool(side:String, entries:Array<Dynamic>):Void {
		var keep = Std.int(setting("spool_keep", 200));
		while (entries.length > keep && entries[0].status != "pending" && entries[0].status != "resuming")
			entries.shift();
		writeJson(stateDir(side) + "/spool.json", entries);
	}

	/**
		Drain the side's retalk mailbox into its spool. `retalk receive` is
		destructive (the relay never serves a message twice), so this always
		runs under the side's lock and writes the spool before returning.
		Messages already in the spool (same id) are ignored. Returns how many were new.
	**/
	static function fetch(side:String):Int {
		var conf = sideConfig(side);
		var added = 0;
		withLock(stateDir(side) + "/spool.lock", true, function() {
			var messages:Array<Message>;
			if (conf.inbox_file != null) {
				messages = readInbox(side, conf);
			} else {
				var result = run([expand(setting("retalk", "retalk")), "receive", "--dir", expand(conf.identity_dir), "--peer", conf.peer, "--quiet", "--save"],
					null, setting("retalk_timeout_seconds", 30), false);
				messages = Policy.parseReceive(result.out);
				if (result.code != 0 && messages.length == 0) {
					log(side, "fetch_failed", {code: result.code, detail: firstLine(result.err)});
					return;
				}
			}
			var entries = spool(side);
			var known = new Map<String, Bool>();
			for (entry in entries)
				known.set(entry.id, true);
			for (message in messages) {
				if (known.exists(message.id)) {
					log(side, "duplicate_ignored", {id: message.id});
					continue;
				}
				known.set(message.id, true);
				entries.push({
					id: message.id,
					from: message.from,
					name: message.name,
					text: message.text,
					hop: message.hop,
					received_at: now(),
					status: "pending",
					attempts: 0
				});
				added++;
				log(side, "received", {id: message.id, hop: message.hop});
			}
			saveSpool(side, entries);
		});
		return added;
	}

	/**
		Read new records from an inbox file another receiver already fills
		(for example the agent-talk follower), without calling `retalk receive`:
		two destructive readers on one mailbox would split its messages. A byte
		cursor in the side's state skips lines already read; a file that shrank
		is read again from the start (the spool still deduplicates by id).
	**/
	static function readInbox(side:String, conf:Dynamic):Array<Message> {
		var path = expand(conf.inbox_file);
		if (!FileSystem.exists(path))
			return [];
		var cursorPath = stateDir(side) + "/inbox-cursor.json";
		var cursor:Dynamic = readJson(cursorPath, {offset: 0});
		var offset:Int = cursor.offset == null ? 0 : cursor.offset;
		var size:Int = FileSystem.stat(path).size;
		if (size < offset)
			offset = 0;
		var chunk:String = Syntax.code("_retalk_bridge_read_from({0}, {1})", path, offset);
		var complete = chunk.lastIndexOf("\n") + 1; // leave a half-written last line for next time
		var body = chunk.substr(0, complete);
		writeJson(cursorPath, {offset: offset + Syntax.code("len({0}.encode('utf-8'))", body)});
		var senders:Array<String> = [conf.peer];
		if (conf.peer_fingerprint != null)
			senders.push(conf.peer_fingerprint);
		return Policy.parseInbox(body, senders, conf.inbox_since == null ? "" : conf.inbox_since);
	}

	static function firstLine(text:String):String {
		var lines = StringTools.trim(text).split("\n");
		var line = lines.length > 0 ? lines[lines.length - 1] : "";
		return line.length > 200 ? line.substr(0, 200) : line;
	}

	static function toMessage(entry:Dynamic):Message {
		return {id: entry.id, from: entry.from, name: entry.name, text: entry.text, hop: entry.hop};
	}

	// ---------------------------------------------------------------- send

	static function send(side:String, text:String, hop:Int):Bool {
		var conf = sideConfig(side);
		var body = hop > 0 ? Policy.markHop(text, hop) : text;
		var result = run([expand(setting("retalk", "retalk")), "send", "--dir", expand(conf.identity_dir), "--peer", conf.peer, "--save", "--", body], null,
			setting("retalk_timeout_seconds", 30), false);
		var receipt:Dynamic = try Policy.parseJson(StringTools.trim(result.out)) catch (e:Dynamic) null;
		if (result.code != 0 || receipt == null) {
			log(side, "send_failed", {code: result.code, detail: firstLine(result.err)});
			return false;
		}
		log(side, "sent", {id: receipt.id, hop: hop});
		Sys.println(Json.stringify({id: receipt.id, to: conf.peer, hop: hop}));
		return true;
	}

	// ---------------------------------------------------------------- hooks

	static function hookAllowed(conf:Dynamic, cwd:String):Bool {
		var dirs:Array<String> = conf.hook_cwds == null ? [] : conf.hook_cwds;
		for (dir in dirs) {
			if (dir == "*")
				return true;
			var base = expand(dir);
			if (cwd == base || StringTools.startsWith(cwd, StringTools.endsWith(base, "/") ? base : base + "/"))
				return true;
		}
		return false;
	}

	static function hook(side:String):Void {
		if (Sys.getEnv("RETALK_BRIDGE_CHILD") == "1")
			return; // a run the watcher started already has the messages in its prompt
		var input = Sys.stdin().readAll().toString();
		var event:Dynamic = try Policy.parseJson(input) catch (e:Dynamic) null;
		if (event == null)
			return;
		var conf = sideConfig(side);
		var cwd:String = event.cwd == null ? Sys.getCwd() : event.cwd;
		if (!hookAllowed(conf, cwd))
			return;
		var name:String = event.hook_event_name == null ? "" : event.hook_event_name;
		writeJson(stateDir(side) + "/session.json", {
			session_id: event.session_id,
			cwd: cwd,
			event: name,
			at: now()
		});
		if (name == "SessionEnd")
			return;
		var stop = name == "Stop";
		if (stop && event.stop_hook_active == true)
			return; // this turn already continued because of a Stop hook: block at most once
		try fetch(side) catch (e:Dynamic) log(side, "fetch_failed", {detail: Std.string(e)});
		var maxHops = Std.int(setting("max_hops", 1));
		var fresh:Array<Message> = [];
		var notes:Array<String> = [];
		withLock(stateDir(side) + "/spool.lock", true, function() {
			var entries = spool(side);
			for (entry in entries) {
				// Stop keeps the agent going only for messages it may still answer; the rest wait for the next prompt.
				var deliver = if (stop) entry.status == "pending" && Policy.replyAllowed(entry.hop, maxHops) else entry.status == "pending"
					|| entry.status == "held";
				if (deliver) {
					fresh.push(toMessage(entry));
					entry.status = "delivered";
					entry.delivered_by = "hook:" + name;
				}
			}
			if (!stop || fresh.length > 0)
				for (entry in entries)
					if ((entry.status == "answered" || entry.status == "reply_failed") && entry.noted != true) {
						notes.push(entry.id + ": " + entry.reply_summary);
						entry.noted = true;
					}
			if (fresh.length > 0 || notes.length > 0)
				saveSpool(side, entries);
		});
		if (fresh.length == 0 && notes.length == 0)
			return;
		var top = 0;
		for (message in fresh)
			if (message.hop > top)
				top = message.hop;
		var sendCommand = 'python3 ${haxe.SysTools.quoteUnixArg(scriptPath())} send --side $side --hop ${top + 1} --';
		var context = Policy.hookContext(conf.peer, fresh, notes, sendCommand, Policy.replyAllowed(top, maxHops));
		log(side, "hook_delivered", {hook: name, messages: [for (m in fresh) m.id], notes: notes.length});
		if (stop) {
			Sys.println(Json.stringify({decision: "block", reason: context}));
		} else {
			Sys.println(Json.stringify({hookSpecificOutput: {hookEventName: name, additionalContext: context}}));
		}
	}

	static function scriptPath():String {
		return Syntax.code("__import__('os').path.abspath(__import__('sys').argv[0])");
	}

	// ---------------------------------------------------------------- watcher

	static function tick(side:String):Void {
		var conf = sideConfig(side);
		if (conf.auto_resume != true)
			return;
		try fetch(side) catch (e:Dynamic) log(side, "fetch_failed", {detail: Std.string(e)});
		var dir = stateDir(side);
		var waiting = 0;
		withLock(dir + "/spool.lock", true, function() {
			var entries = spool(side);
			var pending = [for (entry in entries) if (entry.status == "pending") entry].length;
			waiting = runnable(side, entries).length;
			if (waiting != pending)
				saveSpool(side, entries);
			// A claim left by a run that crashed is released once resume.lock is free (see claim).
			for (entry in entries)
				if (entry.status == "resuming")
					waiting++;
		});
		if (waiting == 0)
			return;

		var health:Dynamic = readJson(dir + "/health.json", {});
		var t = now();
		var benchedUntil:Float = health.benched_until == null ? 0 : health.benched_until;
		if (benchedUntil > t) {
			log(side, "skipped_benched", {until: benchedUntil, pending: waiting});
			return;
		}
		var circuitUntil:Float = health.circuit_open_until == null ? 0 : health.circuit_open_until;
		if (circuitUntil > t) {
			log(side, "skipped_circuit_open", {until: circuitUntil, pending: waiting});
			return;
		}
		var resumes:Array<Float> = health.resumes == null ? [] : health.resumes;
		var perHour = Std.int(setting("max_resumes_per_hour", 2));
		if (Policy.recentCount(resumes, t, 3600) >= perHour) {
			log(side, "skipped_hourly_cap", {cap: perHour, pending: waiting});
			return;
		}
		if (conf.cli == "codex") {
			var until = codexExhaustedUntil(t);
			if (until > t) {
				health.benched_until = until;
				health.bench_reason = "codex rate_limits at 100% in the latest session log";
				writeJson(dir + "/health.json", health);
				log(side, "benched_precheck", {until: until});
				return;
			}
		}
		var ran = withLock(dir + "/resume.lock", false, function() resume(side, conf, health));
		if (!ran)
			log(side, "skipped_resume_in_progress", null);
	}

	/** Mark pending entries past the hop limit `held` and those out of attempts `dead`; return the pending rest. **/
	static function runnable(side:String, entries:Array<Dynamic>):Array<Dynamic> {
		var maxHops = Std.int(setting("max_hops", 1));
		var maxAttempts = Std.int(setting("max_attempts_per_message", 2));
		var batch:Array<Dynamic> = [];
		for (entry in entries) {
			if (entry.status != "pending")
				continue;
			if (!Policy.shouldResume(entry.hop, maxHops)) {
				entry.status = "held"; // past the hop limit: shown to a live session at its next prompt
				log(side, "hop_limit_held", {id: entry.id, hop: entry.hop});
			} else if (entry.attempts >= maxAttempts) {
				entry.status = "dead";
				log(side, "gave_up", {id: entry.id, attempts: entry.attempts});
			} else {
				batch.push(entry);
			}
		}
		return batch;
	}

	/**
		Claim the runnable entries as `resuming`, so hooks leave them alone while
		the CLI runs, and count the attempt. Called only while holding resume.lock,
		so any entry already `resuming` belongs to a run that died: it is released first.
	**/
	static function claim(side:String):Array<Dynamic> {
		var batch:Array<Dynamic> = [];
		withLock(stateDir(side) + "/spool.lock", true, function() {
			var entries = spool(side);
			for (entry in entries)
				if (entry.status == "resuming") {
					entry.status = "pending";
					log(side, "stale_claim_released", {id: entry.id});
				}
			batch = runnable(side, entries);
			for (entry in batch) {
				entry.status = "resuming";
				// Counted before running, so a crash mid-run can never retry forever.
				entry.attempts = entry.attempts + 1;
			}
			saveSpool(side, entries);
		});
		return batch;
	}

	/** Pick the session to wake: the bridge's own session by default, or the last hook-seen session when it has gone quiet. **/
	static function targetSession(side:String, conf:Dynamic):{id:String, cwd:String} {
		var fallbackCwd = expand(conf.bridge_cwd == null ? "~/.local/state/retalk-bridge/" + side + "-workdir" : conf.bridge_cwd);
		if (!FileSystem.exists(fallbackCwd))
			FileSystem.createDirectory(fallbackCwd);
		if (conf.resume_target == "latest") {
			var seen:Dynamic = readJson(stateDir(side) + "/session.json", null);
			var idle = Std.parseFloat(Std.string(setting("idle_seconds", 300)));
			if (seen != null && seen.session_id != null && (seen.event == "Stop" || seen.event == "SessionEnd") && now() - seen.at >= idle)
				return {id: seen.session_id, cwd: seen.cwd};
		}
		var own:Dynamic = readJson(stateDir(side) + "/bridge-session.json", null);
		if (own != null && own.session_id != null && own.session_id != "")
			return {id: own.session_id, cwd: own.cwd == null ? fallbackCwd : own.cwd};
		return {id: "", cwd: fallbackCwd};
	}

	static function resume(side:String, conf:Dynamic, health:Dynamic):Void {
		var batch = claim(side);
		if (batch.length == 0)
			return;
		var dir = stateDir(side);
		var maxHops = Std.int(setting("max_hops", 1));
		var top = 0;
		for (entry in batch)
			if (entry.hop > top)
				top = entry.hop;
		var mayReply = Policy.replyAllowed(top, maxHops);
		var ids = [for (entry in batch) entry.id];
		function settle(status:String, summary:String)
			updateEntries(side, ids, function(entry) {
				entry.status = status;
				entry.reply_summary = summary;
			});
		var target = targetSession(side, conf);
		var prompt = Policy.resumePrompt(conf.peer, [for (entry in batch) toMessage(entry)], mayReply);
		var binary = expand(conf.binary == null ? conf.cli : conf.binary);
		var extra:Array<String> = conf.extra_args == null ? [] : conf.extra_args;
		var command:Array<String>;
		if (conf.cli == "claude") {
			// extra_args go first: a variadic flag such as --disallowedTools must not swallow the prompt.
			command = [binary, "-p"].concat(extra).concat(["--output-format", "json"]);
			if (target.id != "")
				command = command.concat(["--resume", target.id]);
			command.push(prompt);
		} else {
			command = target.id != "" ? [binary, "exec", "resume", target.id, "--json", "--skip-git-repo-check", "-c", "sandbox_mode=\"read-only\""] : [
				binary, "exec", "--json", "--skip-git-repo-check", "-s", "read-only", "-C", target.cwd
			];
			command = command.concat(extra);
			command.push(prompt);
		}
		var t = now();
		log(side, "resume_started", {messages: ids, session: target.id == "" ? "new" : target.id, may_reply: mayReply});
		var result = run(command, target.cwd, setting("resume_timeout_seconds", 600), true);
		var outcome:Outcome = conf.cli == "claude" ? Policy.classifyClaude(result.code, result.out, result.err,
			now()) : Policy.classifyCodex(result.code, result.out, result.err, now());
		var resumes:Array<Float> = health.resumes == null ? [] : health.resumes;
		resumes = [for (s in resumes) if (s > t - 86400) s];
		resumes.push(t);
		health.resumes = resumes;
		switch (outcome.kind) {
			case "ok":
				health.failures = 0;
				if (outcome.sessionId != "" && (target.id == "" || target.id == outcome.sessionId || conf.resume_target != "latest"))
					writeJson(dir + "/bridge-session.json", {session_id: outcome.sessionId, cwd: target.cwd});
				log(side, "resume_ok", {session: outcome.sessionId, exit_code: result.code, reply: clip(outcome.reply, 500)});
				if (Policy.isNoReply(outcome.reply)) {
					settle("answered", "(no reply)");
				} else if (!mayReply) {
					settle("answered", "reply not sent (hop limit): " + clip(outcome.reply, 300));
					log(side, "reply_suppressed_hop_limit", {hop: top + 1, max_hops: maxHops});
				} else if (send(side, outcome.reply, top + 1)) {
					settle("answered", "replied: " + clip(outcome.reply, 300));
				} else {
					// Shown to the live session like an answer, so a person can resend it.
					settle("reply_failed", "reply NOT sent (retalk send failed): " + clip(outcome.reply, 300));
					log(side, "reply_failed", {messages: ids});
					countFailure(side, health);
				}
			case "rate_limited":
				var backoff = Std.parseFloat(Std.string(setting("default_backoff_minutes", 30))) * 60;
				var until = outcome.resetAt > now() ? outcome.resetAt : now() + backoff;
				health.benched_until = until;
				health.bench_reason = outcome.detail;
				// The provider refused before doing work: this attempt does not count against the message.
				updateEntries(side, ids, function(entry) {
					entry.status = "pending";
					entry.attempts = entry.attempts - 1;
				});
				log(side, "rate_limited", {until: until, reset_from_output: outcome.resetAt > 0, exit_code: result.code, detail: outcome.detail});
			default:
				updateEntries(side, ids, function(entry) entry.status = "pending");
				countFailure(side, health);
				log(side, "resume_failed", {exit_code: result.code, detail: outcome.detail});
		}
		writeJson(dir + "/health.json", health);
	}

	/** Count one failed run or send towards the circuit breaker. **/
	static function countFailure(side:String, health:Dynamic):Void {
		var failures:Int = health.failures == null ? 0 : health.failures;
		failures++;
		health.failures = failures;
		if (failures >= Std.int(setting("circuit_breaker_failures", 3))) {
			health.circuit_open_until = now() + Std.parseFloat(Std.string(setting("circuit_open_minutes", 60))) * 60;
			health.failures = 0;
			log(side, "circuit_opened", {until: health.circuit_open_until});
		}
	}

	static function clip(text:String, limit:Int):String {
		return text.length > limit ? text.substr(0, limit) + "…" : text;
	}

	static function updateEntries(side:String, ids:Array<String>, change:Dynamic->Void):Void {
		withLock(stateDir(side) + "/spool.lock", true, function() {
			var entries = spool(side);
			for (entry in entries)
				if (ids.indexOf(entry.id) >= 0)
					change(entry);
			saveSpool(side, entries);
		});
	}

	/** Read the newest Codex session log's last `rate_limits` snapshot without calling a model. **/
	static function codexExhaustedUntil(t:Float):Float {
		var root = expand(setting("codex_sessions_dir", "~/.codex/sessions"));
		var snapshot:Null<String> = Syntax.code("_retalk_bridge_codex_snapshot({0})", root);
		if (snapshot == null)
			return 0;
		return Policy.codexExhaustedUntil(try Policy.parseJson(snapshot) catch (e:Dynamic) null, t);
	}

	// ---------------------------------------------------------------- status

	static function status():Void {
		var report:Dynamic = {config: configPath, sides: {}};
		for (side in sideNames()) {
			var dir = stateDir(side);
			var counts:Dynamic = {};
			for (entry in spool(side)) {
				var key:String = entry.status;
				var current:Null<Int> = Reflect.field(counts, key);
				Reflect.setField(counts, key, current == null ? 1 : current + 1);
			}
			var health:Dynamic = readJson(dir + "/health.json", {});
			Reflect.setField(report.sides, side, {
				spool: counts,
				benched_until: health.benched_until,
				circuit_open_until: health.circuit_open_until,
				resumes_last_hour: Policy.recentCount(health.resumes == null ? [] : health.resumes, now(), 3600),
				bridge_session: readJson(dir + "/bridge-session.json", null),
				last_hook_session: readJson(dir + "/session.json", null)
			});
		}
		Sys.println(Json.stringify(report, null, " "));
	}

	// ---------------------------------------------------------------- install

	static inline var MARKER = "retalk_bridge.py hook";

	/** Merge (or remove) the bridge's hook entries; every other hook is kept as it was. **/
	static function installHooks(options:Map<String, String>, add:Bool):Void {
		var command = options.get("command");
		if (add && command == null)
			usage("install-hooks needs --command (the path to retalk_bridge.py)");
		var claude = options.get("claude-settings");
		if (claude != null)
			mergeHookFile(claude, ["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"], add ? command + " hook --side claude" : null, false);
		var codex = options.get("codex-hooks");
		if (codex != null)
			mergeHookFile(codex, ["SessionStart", "UserPromptSubmit", "Stop"], add ? command + " hook --side codex" : null, true);
		if (claude == null && codex == null)
			usage("give --claude-settings and/or --codex-hooks");
	}

	static function mergeHookFile(path:String, events:Array<String>, hookCommand:Null<String>, codex:Bool):Void {
		var data:Dynamic = FileSystem.exists(path) ? Policy.parseJson(File.getContent(path)) : {};
		if (data.hooks == null)
			data.hooks = {};
		var changed = false;
		for (event in Reflect.fields(data.hooks)) {
			var groups:Array<Dynamic> = Reflect.field(data.hooks, event);
			var kept = [for (group in groups) if (!isOurs(group)) group];
			if (kept.length != groups.length) {
				changed = true;
				if (kept.length == 0)
					Reflect.deleteField(data.hooks, event);
				else
					Reflect.setField(data.hooks, event, kept);
			}
		}
		if (hookCommand != null) {
			for (event in events) {
				var groups:Array<Dynamic> = Reflect.field(data.hooks, event);
				if (groups == null)
					groups = [];
				var handler:Dynamic = {type: "command", command: hookCommand, timeout: 30};
				if (codex)
					handler.statusMessage = "Checking retalk messages";
				groups.push({hooks: [handler]});
				Reflect.setField(data.hooks, event, groups);
			}
			changed = true;
		}
		if (Reflect.fields(data.hooks).length == 0)
			Reflect.deleteField(data, "hooks");
		if (!changed && hookCommand == null) {
			Sys.println("unchanged " + path);
			return;
		}
		var dirName = haxe.io.Path.directory(path);
		if (dirName != "" && !FileSystem.exists(dirName))
			FileSystem.createDirectory(dirName);
		var tmp = path + ".retalk-bridge.tmp";
		File.saveContent(tmp, Json.stringify(data, null, "  ") + "\n");
		if (FileSystem.exists(path))
			Syntax.code("__import__('shutil').copymode({0}, {1})", path, tmp);
		FileSystem.rename(tmp, path);
		Sys.println((hookCommand == null ? "removed bridge hooks from " : "merged bridge hooks into ") + path);
	}

	static function isOurs(group:Dynamic):Bool {
		var handlers:Array<Dynamic> = group == null || group.hooks == null ? [] : group.hooks;
		for (handler in handlers)
			if (handler.command != null && Std.string(handler.command).indexOf(MARKER) >= 0)
				return true;
		return false;
	}

	static function __init__():Void {
		Syntax.code("def _retalk_bridge_read_from(path, offset):
    with open(path, 'rb') as handle:
        handle.seek(offset)
        return handle.read().decode('utf-8', 'replace')");
		Syntax.code("def _retalk_bridge_codex_snapshot(root):
    import os, json
    newest, newest_mtime = None, -1.0
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith('.jsonl'):
                path = os.path.join(base, name)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if mtime > newest_mtime:
                    newest, newest_mtime = path, mtime
    if newest is None:
        return None
    try:
        with open(newest, 'rb') as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 262144))
            tail = handle.read().decode('utf-8', 'replace')
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '\"rate_limits\"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        stack = [record]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if isinstance(item.get('rate_limits'), dict):
                    return json.dumps(item['rate_limits'])
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    return None");
	}
}
