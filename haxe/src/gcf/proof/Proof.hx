package gcf.proof;

/**
	Toolchain proof shared by the Python and Node entry points.

	It has no product behavior. It exists so `scripts/check-haxe.sh` can show
	that one Haxe source compiles to both targets and that both generated
	programs print the same thing.
**/
class Proof {
	/**
		Describe a run: the target name, the arguments in order, and the
		arguments reversed. The caller's array is not modified.
	**/
	public static function describe(target:String, args:Array<String>):String {
		var reversed = args.copy();
		reversed.reverse();
		return 'proof ok: target=$target, args=${args.join("|")}, reversed=${reversed.join("|")}';
	}
}
