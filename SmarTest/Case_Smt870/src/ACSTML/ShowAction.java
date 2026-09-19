package ACSTML;

import javax.swing.JOptionPane;

import xoc.dta.TestMethod;

public class ShowAction extends TestMethod {

    @Override
    public void execute() {
        // TODO Auto-generated method stub

        if(global_variable.hasAction==true)
        {
            JOptionPane.showMessageDialog(null, global_variable.ActionStr);
        }
    }

}
