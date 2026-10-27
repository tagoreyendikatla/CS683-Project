public class BranchUnpredictable {
    public static void main(String[] args) {
        Thread.currentThread().setName("checkpoint-main");
        int state = 1;
        int total = 0;
        for (int index = 0; index < 10_000_000; index++) {
            state = 1_103_515_245 * state + 12_345;
            if (state < 0) {
                total++;
            } else {
                total--;
            }
        }

        System.out.println(total);
    }
}
