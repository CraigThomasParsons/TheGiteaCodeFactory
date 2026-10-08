package gcf.proof;

import js.Node;

/**
	Node entry point of the toolchain proof. It uses the hxnodejs bindings
	(`js.Node`), so building it also proves the pinned library resolves.
**/
class HelloNode {
	static function main():Void {
		Node.console.log(Proof.describe("node", Node.process.argv.slice(2)));
	}
}
