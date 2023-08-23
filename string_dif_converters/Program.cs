namespace string_dif_converters
{
    internal class Program
        // PUSH FOR SATAN
    {
        static void Main(string[] args)
        {
            bool running = true;

            while (running)
            {
                Console.WriteLine("Vælg en funktion");
                Console.WriteLine("1. Baglæns sætning") ;
                Console.WriteLine("2. Konverter bogstaver");
                Console.WriteLine("3. Afslut");

                int valg = Convert.ToInt32(Console.ReadLine());

                switch (valg)
                {
                    case 1:
                        Console.WriteLine("Skriv en sætning");
                        string input = Console.ReadLine();
                        switcharoo(input);
                        break;

                    case 2:
                        Console.WriteLine("Skriv en sætning");
                        string inputSentence = Console.ReadLine();

                        Console.WriteLine("Vælg et bogstav, du vil erstatte");
                        char oldChar = Console.ReadKey().KeyChar;

                        Console.WriteLine("\nVælg det nye bogstav");
                        char newChar = Console.ReadKey().KeyChar;

                        string modifiedSentence = erstatBogstav(inputSentence, oldChar, newChar);
                        Console.WriteLine("\nÆndret sætning: " + modifiedSentence);
                        break;


                    case 3:
                        break;

                    default:
                        Console.WriteLine("Ugyldigt valg");
                        break;
                }
            }
           
        }
        // string methods 

        //baglæns sætning
        static void switcharoo(string s)
        {
           string input = Console.ReadLine();
           for (int i = s.Length- 1;  i >= 0; i--)
            {
                Console.Write(s[i]);
            }
            Console.WriteLine();

        }
        // converter bogstaver om til et andet bogstav. 
        static string erstatBogstav(string sentence, char oldChar, char newChar)
        {
            char[] sentenceArray = sentence.ToCharArray();
            for (int i = 0; i < sentenceArray.Length; i++)
            {
                if (sentenceArray[i] == oldChar)
                {
                    sentenceArray[i] = newChar;
                }
            }
            return new string(sentenceArray);
        }

        // 
    }
}