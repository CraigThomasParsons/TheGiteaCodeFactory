package gcf.retalkbridge;

import utest.Assert;

/** Target-neutral tests of the retalk bridge's pure decisions. **/
class PolicyTest extends utest.Test {
	static inline var NOW = 1800000000.0;

	function testParseReceiveSkipsNonChatRecords() {
		var output = '{"id":"a1","from":"f","name":"codex","text":"hi"}\n'
			+ '{"id":"c1","from":"f","name":"x","kind":"contact","card":{}}\n'
			+ 'not json\n\n'
			+ '{"id":"a2","from":"f","name":"codex","text":"[retalk-bridge hop=2] pong"}\n';
		var messages = Policy.parseReceive(output);
		Assert.equals(2, messages.length);
		Assert.equals("hi", messages[0].text);
		Assert.equals(0, messages[0].hop);
		Assert.equals("pong", messages[1].text);
		Assert.equals(2, messages[1].hop);
	}

	function testHopMarking() {
		Assert.equals("[retalk-bridge hop=3] ok", Policy.markHop("ok", 3));
		Assert.equals(3, Policy.hopOf(Policy.markHop("ok", 3)));
		Assert.equals(0, Policy.hopOf("text mentioning [retalk-bridge hop=3] later"));
		Assert.isTrue(Policy.shouldResume(1, 1));
		Assert.isFalse(Policy.shouldResume(2, 1));
		Assert.isTrue(Policy.replyAllowed(0, 1));
		Assert.isFalse(Policy.replyAllowed(1, 1));
	}

	function testRecentCount() {
		Assert.equals(2, Policy.recentCount([NOW - 10, NOW - 3599, NOW - 3601, NOW + 5], NOW, 3600));
	}

	function testLimitText() {
		Assert.isTrue(Policy.limitText("You've hit your session limit · resets 5:20pm (America/Toronto)"));
		Assert.isTrue(Policy.limitText("RESOURCE_EXHAUSTED (code 429): Individual quota reached."));
		Assert.isTrue(Policy.limitText("Rate limit exceeded"));
		Assert.isFalse(Policy.limitText("tests failed: 3 errors"));
	}

	function testParseResetForms() {
		Assert.equals(1773853402.0, Policy.parseReset('"resets_at": 1773853402', NOW));
		Assert.equals(NOW + 2 * 3600 + 40 * 60 + 11, Policy.parseReset("Resets in 2h40m11s.", NOW));
		Assert.equals(NOW + 15 * 60, Policy.parseReset("try again in 15 minutes", NOW));
		Assert.equals(0.0, Policy.parseReset("no reset here", NOW));
		var clock = Policy.parseReset("resets 5:20pm (America/Toronto)", NOW);
		Assert.isTrue(clock > NOW && clock <= NOW + 86400);
		var at = Date.fromTime(clock * 1000);
		Assert.equals(17, at.getHours());
		Assert.equals(20, at.getMinutes());
	}

	function testClassifyClaude() {
		var ok = Policy.classifyClaude(0, '{"type":"result","is_error":false,"result":" pong ","session_id":"s1"}', "", NOW);
		Assert.equals("ok", ok.kind);
		Assert.equals("pong", ok.reply);
		Assert.equals("s1", ok.sessionId);
		var limited = Policy.classifyClaude(1, '{"type":"result","is_error":true,"result":"You\'ve hit your session limit · resets 5:20pm (America/Toronto)","session_id":"s1"}', "", NOW);
		Assert.equals("rate_limited", limited.kind);
		Assert.isTrue(limited.resetAt > NOW);
		var quietLimit = Policy.classifyClaude(0, '{"type":"result","is_error":false,"result":"Claude AI usage limit reached","session_id":"s1"}', "", NOW);
		Assert.equals("rate_limited", quietLimit.kind);
		var talkAboutLimits = Policy.classifyClaude(0, '{"type":"result","is_error":false,"result":"The API has a rate limit of 10 rps.","session_id":"s1"}', "", NOW);
		Assert.equals("ok", talkAboutLimits.kind);
		Assert.equals("failed", Policy.classifyClaude(1, "", "segfault", NOW).kind);
		Assert.equals("failed", Policy.classifyClaude(0, "", "", NOW).kind);
	}

	function testClassifyCodex() {
		var stream = '{"type":"thread.started","thread_id":"t1"}\n{"type":"item.completed","item":{"type":"agent_message","text":"pong"}}\n{"type":"turn.completed"}';
		var ok = Policy.classifyCodex(0, stream, "", NOW);
		Assert.equals("ok", ok.kind);
		Assert.equals("pong", ok.reply);
		Assert.equals("t1", ok.sessionId);
		var limit = '{"type":"thread.started","thread_id":"t1"}\n{"type":"turn.failed","error":{"message":"You\'ve hit your usage limit. Try again in 1h."}}';
		var limited = Policy.classifyCodex(1, limit, "", NOW);
		Assert.equals("rate_limited", limited.kind);
		Assert.equals(NOW + 3600, limited.resetAt);
		Assert.equals("failed", Policy.classifyCodex(1, '{"type":"turn.failed","error":{"message":"stream disconnected"}}', "", NOW).kind);
	}

	function testCodexExhaustedUntil() {
		var snapshot = {primary: {used_percent: 100.0, resets_at: NOW + 60}, secondary: {used_percent: 40.0, resets_at: NOW + 999}};
		Assert.equals(NOW + 60, Policy.codexExhaustedUntil(snapshot, NOW));
		Assert.equals(0.0, Policy.codexExhaustedUntil({primary: {used_percent: 99.0, resets_at: NOW + 60}}, NOW));
		Assert.equals(0.0, Policy.codexExhaustedUntil({primary: {used_percent: 100.0, resets_at: NOW - 60}}, NOW));
		Assert.equals(0.0, Policy.codexExhaustedUntil(null, NOW));
	}

	function testPromptsAndNoReply() {
		var messages = [{id: "m1", from: "f", name: "codex", text: "pong", hop: 1}];
		Assert.isTrue(Policy.resumePrompt("codex", messages, true).indexOf("sent back to the peer verbatim") > 0);
		Assert.isTrue(Policy.resumePrompt("codex", messages, false).indexOf("nothing you write now is sent") > 0);
		Assert.isTrue(Policy.hookContext("codex", messages, [], "send-cmd").indexOf("To reply, run: send-cmd") > 0);
		Assert.isTrue(Policy.isNoReply(" NO_REPLY "));
		Assert.isTrue(Policy.isNoReply(""));
		Assert.isFalse(Policy.isNoReply("pong"));
	}

	function testParseInboxFiltersSenderAndTime() {
		var output = '{"id":"o1","from":"aa","name":"codex","text":"old","ts":"2026-10-17T01:00:00Z"}\n'
			+ '{"id":"n1","from":"aa","name":"codex","text":"new","ts":"2026-10-17T01:43:56Z"}\n'
			+ '{"id":"x1","from":"bb","name":"stranger","text":"spam","ts":"2026-10-17T01:50:00Z"}\n'
			+ '{"id":"c1","from":"aa","name":"codex","kind":"contact","card":{},"ts":"2026-10-17T01:50:00Z"}\n'
			+ '{"id":"f1","from":"aa","name":"renamed","text":"by fingerprint","ts":"2026-10-17T01:51:00Z"}\n';
		var kept = Policy.parseInbox(output, ["codex", "aa"], "2026-10-17T01:43:00Z");
		Assert.equals(2, kept.length);
		Assert.equals("n1", kept[0].id);
		Assert.equals("f1", kept[1].id);
		Assert.equals(3, Policy.parseInbox(output, ["codex", "aa"], "").length);
	}
}
