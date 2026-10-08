package gcf.proof;

import utest.Assert;

class ProofTest extends utest.Test {
	function testDescribesTargetAndArgumentsInBothOrders() {
		Assert.equals("proof ok: target=python, args=a|b|c, reversed=c|b|a", Proof.describe("python", ["a", "b", "c"]));
	}

	function testLeavesTheCallersArgumentsUnchanged() {
		var args = ["x", "y"];
		Proof.describe("node", args);
		Assert.same(["x", "y"], args);
	}

	function testHandlesNoArguments() {
		Assert.equals("proof ok: target=node, args=, reversed=", Proof.describe("node", []));
	}
}
