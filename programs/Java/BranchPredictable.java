public class BranchPredictable {
    public static void main(String[] args) {
        Thread.currentThread().setName("checkpoint-main");
        int total = 0;
        for (int index = 0; index < 10_000_000; index++) {
            if ((index & 63) != 0) {
                total++;
            } else {
                total--;
            }
        }

        System.out.println(total);
    }
}
