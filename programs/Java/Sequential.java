public class Sequential {
    public static void main(String[] args) {
        Thread.currentThread().setName("checkpoint-main");
        double[] values = new double[65536];
        for (int index = 0; index < values.length; index++) {
            values[index] = index;
        }

        double totalSum = 0.0;
        for (int repetition = 0; repetition < 256; repetition++) {
            for (double value : values) {
                totalSum += value;
            }
        }

        System.out.println(totalSum);
    }
}