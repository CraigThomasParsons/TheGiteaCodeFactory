/** Runs every utest suite; scripts/check-haxe.sh runs it on each target in haxe/test/. **/
class TestMain {
	static function main():Void {
		utest.UTest.run([new gcf.proof.ProofTest()]);
	}
}
