package gcf.proof;

/** Python entry point of the toolchain proof; prints `Proof.describe` for its arguments. **/
class HelloPython {
	static function main():Void {
		Sys.println(Proof.describe("python", Sys.args()));
	}
}
